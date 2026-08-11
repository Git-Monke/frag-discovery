import { useEffect, useMemo, useRef, useState } from "react";
import { FragranceDetail } from "@/components/detail/FragranceDetail";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { RequireAuth } from "@/components/auth/RequireAuth";
import {
	useFavoriteToggle,
	useFavorites,
	useFeedback,
	useFragrance,
	useRecommend,
	useRemoveFeedback,
} from "@/hooks/queries";
import { avif, fmt, fmtBayes, fmtRating } from "@/lib/utils";
import type { FeedbackAction, Fragrance, RecommendResult } from "@/lib/types";
import { RotateCcw } from "lucide-react";

const BATCH = 10;
const REFETCH_AT = 3;
// Matches REC_MIN_FAVORITES in app.py: favorites + "interested" ratings count.
const REC_MIN_POSITIVE = 5;

interface HistoryEntry {
	type: FeedbackAction;
	frag: RecommendResult;
}

/** The 3-level taste scale (weights mirror FEEDBACK_WEIGHTS in app.py,
 * RECO_LEVELS=3): Pass / Interested / Love. */
const LEVELS: {
	action: FeedbackAction;
	label: string;
	title: string;
	weight: number;
}[] = [
	{
		action: "pass",
		label: "Pass",
		title: "Not interested in trying — just pass",
		weight: -1.0,
	},
	{
		action: "interested",
		label: "Interested",
		title: "I'd like to try it",
		weight: 1.0,
	},
	{ action: "love", label: "Love", title: "I know I love it", weight: 2.0 },
];

const LEVEL_STYLES: Record<FeedbackAction, string> = {
	pass: "border-transparent bg-muted text-muted-foreground hover:bg-muted/80",
	interested:
		"border-bayesian/40 text-bayesian hover:bg-bayesian/10 hover:text-bayesian",
	love: "border-transparent bg-like text-background hover:bg-like/90",
};

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
	return (
		<div className="flex items-baseline gap-1.5">
			<span className="text-[10px] tracking-wider text-muted-foreground uppercase">
				{label}
			</span>
			<span className="font-semibold">{value}</span>
		</div>
	);
}

export default function DiscoverPage() {
	// Feed queue: a prefetched batch of recommendations from /api/recommend.
	// `nonce` is bumped to refetch the next batch when the queue runs low.
	const [queue, setQueue] = useState<RecommendResult[]>([]);
	const [nonce, setNonce] = useState(0);
	const [exhausted, setExhausted] = useState(false);
	// Undo stack for the last Skip / Favorite.
	const [history, setHistory] = useState<HistoryEntry[]>([]);

	const { data: batch, isFetching: fetchingBatch } = useRecommend(BATCH, nonce);
	const fetchingRef = useRef(fetchingBatch);
	fetchingRef.current = fetchingBatch;
	const { data: favData } = useFavorites();
	const feedback = useFeedback();
	const removeFeedback = useRemoveFeedback();
	const favoriteToggle = useFavoriteToggle();

	const current = queue[0] ?? null;
	const currentId = current?.id ?? null;
	const { data: frag, isFetching: fetchingFrag } = useFragrance(currentId);
	const [lastGood, setLastGood] = useState<Fragrance | null>(null);
	useEffect(() => {
		if (frag) setLastGood(frag);
	}, [frag]);

	const coldStart = batch ? batch.profile.cold_start : false;
	const favCount = favData?.count ?? 0;
	const levels = batch?.profile.levels;
	const interestedCount = levels?.interested ?? 0;
	const otherRated = levels ? (levels.pass ?? 0) + (levels.interested ?? 0) : 0;
	const busy =
		feedback.isPending || removeFeedback.isPending || favoriteToggle.isPending;

	// Live set of favorite ids, refreshed after any in-app favorite toggle and
	// on window focus (covers favorites added in another tab).
	const favIds = useMemo(
		() => new Set(favData?.results?.map((r) => r.id) ?? []),
		[favData],
	);

	// Favorites added after a batch was fetched (e.g. from Browse, Favorites,
	// or another tab) must not stay in the feed — drop them from the queue as
	// soon as the favorites list catches up. Undo history is untouched, so an
	// undo of a favorite still restores the card.
	useEffect(() => {
		if (!favIds.size) return;
		setQueue((prev) => {
			const kept = prev.filter((r) => !favIds.has(r.id));
			return kept.length === prev.length ? prev : kept;
		});
	}, [favIds]);

	// Append freshly fetched batches to the queue (dedupe by id). If a fetch
	// adds nothing while the queue is empty, every pool fragrance has been
	// seen. `batch` only changes on fetch completion, so the `queue` from that
	// render is the right snapshot to test exhaustion against.
	useEffect(() => {
		if (!batch) return;
		const queueIds = new Set(queue.map((r) => r.id));
		const fresh = batch.results.filter((r) => !queueIds.has(r.id));
		if (fresh.length === 0 && queue.length === 0) {
			setExhausted(true);
			return;
		}
		setQueue((prev) => {
			const prevIds = new Set(prev.map((r) => r.id));
			const prevFresh = batch.results.filter((r) => !prevIds.has(r.id));
			return prevFresh.length ? [...prev, ...prevFresh] : prev;
		});
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [batch]);

	// Keep the queue topped up: whenever it runs low — after swipes, or after
	// favorites are purged from it — fetch the next batch. Guarded by the
	// in-flight flag and the exhausted terminal state so it can't loop.
	useEffect(() => {
		if (queue.length === 0 || queue.length > REFETCH_AT) return;
		if (fetchingRef.current || exhausted) return;
		setNonce((n) => n + 1);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [queue.length, exhausted]);

	const advance = () => {
		setQueue((prev) => prev.slice(1));
	};

	const doRate = (action: FeedbackAction) => {
		if (!current) return;
		feedback.mutate({ id: current.id, action });
		setHistory((h) => [...h, { type: action, frag: current }]);
		advance();
	};

	const doUndo = () => {
		const last = history[history.length - 1];
		if (!last) return;
		setHistory((h) => h.slice(0, -1));
		setQueue((q) => [last.frag, ...q]);
		// DELETE /api/feedback/<id> removes the rating AND the favorite if it was
		// a love, so one call undoes any level.
		removeFeedback.mutate(last.frag.id);
	};

	// ↓ = Pass, ↑ = Interested, → = Love (undo with Ctrl+Z / the Undo button).
	useEffect(() => {
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "ArrowDown") {
				e.preventDefault();
				doRate("pass");
			} else if (e.key === "ArrowUp") {
				e.preventDefault();
				doRate("interested");
			} else if (e.key === "ArrowRight") {
				e.preventDefault();
				doRate("love");
			}
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	});

	const detail = frag ?? lastGood;
	const detailFrag = detail;
	const loadingFirst = !current && !exhausted && fetchingBatch;

	return (
		<RequireAuth>
			<div className="flex h-full flex-col">
			{/* Header: title + profile stats + undo */}
			<div className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
				<span className="text-sm font-semibold">Discover</span>
				<span className="text-xs text-muted-foreground">
					<span className="font-semibold text-foreground">{fmt(favCount)}</span>{" "}
					favorite{favCount === 1 ? "" : "s"}
					{otherRated > 0 && (
						<>
							{" · "}
							<span className="font-semibold text-foreground">
								{fmt(otherRated)}
							</span>{" "}
							rated
						</>
					)}
				</span>
				<div className="ml-auto flex items-center gap-2">
					{!coldStart && queue.length > 0 && (
						<span className="hidden text-[10px] text-muted-foreground sm:inline">
							↓ Pass · ↑ Interested · → Love
						</span>
					)}
					<Button
						variant="outline"
						size="sm"
						className="h-7 px-2 text-xs"
						disabled={!history.length}
						title="Undo the last Skip / Favorite"
						onClick={doUndo}
					>
						<RotateCcw className="mr-1 size-3.5" /> Undo
					</Button>
				</div>
			</div>

			<div className="min-h-0 flex-1 overflow-y-auto">
				<div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 pb-10">
					{coldStart && (
						<div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
							Teaching the feed your taste —{" "}
							<span className="font-semibold text-foreground">
								Love or mark Interested on at least{" "}
								{Math.max(0, REC_MIN_POSITIVE - (favCount + interestedCount))}{" "}
								more
							</span>{" "}
							fragrance
							{Math.max(0, REC_MIN_POSITIVE - (favCount + interestedCount)) ===
							1
								? ""
								: "s"}
							to unlock personalized recommendations. Showing random picks for
							now.
						</div>
					)}

					{loadingFirst ? (
						<div className="flex flex-col gap-3">
							<Skeleton className="h-64 w-full rounded-xl" />
							<Skeleton className="h-24 w-full rounded-xl" />
						</div>
					) : exhausted ? (
						<div className="flex h-full flex-col items-center justify-center gap-1 py-24 text-sm text-muted-foreground">
							<span>You've seen every fragrance in the catalog</span>
							<span className="text-xs text-muted-foreground/60">
								Check your favorites or reset the model to start over.
							</span>
						</div>
					) : current ? (
						<>
							{/* The card */}
							<div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
								<div className="flex gap-4 p-4">
									{current.image_url && (
										<ImageWithFallback
											src={avif(current.image_url)}
											alt={current.name ?? ""}
											className="h-52 w-40 shrink-0 rounded-lg object-cover"
										/>
									)}
									<div className="min-w-0 flex-1">
										<div className="flex items-start justify-between gap-2">
											<h2 className="text-lg leading-tight font-semibold">
												{current.name ?? "—"}
											</h2>
											{current.p != null ? (
												<span className="shrink-0 rounded-full border border-bayesian/40 bg-bayesian/10 px-2 py-0.5 text-[11px] font-semibold text-bayesian">
													{Math.round(current.p * 100)}% match
												</span>
											) : current.exploration ? (
												<span className="shrink-0 rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground">
													exploring
												</span>
											) : null}
										</div>
										<div className="mt-0.5 text-sm text-muted-foreground">
											{current.brand ?? ""}
											{current.brand && current.year ? " · " : ""}
											{current.year ?? ""}
										</div>
										<div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[13px]">
											<Stat
												label="Rating"
												value={
													<span className="text-primary">
														{fmtRating(current.rating)}
													</span>
												}
											/>
											<Stat label="Votes" value={fmt(current.votes)} />
											<Stat
												label="Bayesian"
												value={
													<span className="text-bayesian">
														{fmtBayes(current.bayesian_score)}
													</span>
												}
											/>
										</div>
										<div className="mt-4 flex gap-2">
											{LEVELS.map(({ action, label, title, weight }) => (
												<Button
													key={action}
													variant="outline"
													size="lg"
													className={`h-11 flex-1 px-1 text-xs ${LEVEL_STYLES[action]}`}
													disabled={busy}
													title={`${title} (${weight > 0 ? "+" : ""}${weight}) — trains the recommender`}
													onClick={() => doRate(action)}
												>
													<span className="font-medium">{label}</span>
													<span className="ml-1 text-[10px] opacity-70">
														{weight > 0 ? "+" : ""}
														{weight}
													</span>
												</Button>
											))}
										</div>
									</div>
								</div>
							</div>

							{/* Full detail below */}
							{detailFrag ? (
								<div className="rounded-xl border border-border bg-card shadow-sm">
									<FragranceDetail
										fragrance={detailFrag}
										hideFavoriteButton
										className="px-4 py-3"
									/>
								</div>
							) : (
								<div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
									<span className="size-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
									Loading details…
								</div>
							)}

							{fetchingFrag && !frag && (
								<span className="sticky bottom-2 self-center rounded-full border border-border bg-card px-3 py-1 text-[10px] text-muted-foreground shadow-sm">
									Loading…
								</span>
							)}
						</>
					) : null}
				</div>
			</div>
		</div>
		</RequireAuth>
	);
}
