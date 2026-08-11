import { useState } from "react";
import { Search } from "lucide-react";
import { FragranceCard } from "@/components/browse/ResultsGrid";
import { FragranceDetail } from "@/components/detail/FragranceDetail";
import { DebouncedTextInput } from "@/components/common/DebouncedTextInput";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useClearFavorites, useFavorites, useFragrance } from "@/hooks/queries";
import { useUIStore } from "@/stores/ui";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { fmt } from "@/lib/utils";

export default function FavoritesPage() {
	// Favorites are ALWAYS ranked by "most likely to be my favorite" (the
	// recommender's P(favorite)); no toggle. Before the model is trained it
	// falls back to most-recent order, with the % badge hidden (p is null).
	const { data, isLoading, isError } = useFavorites("recommend");
	const clear = useClearFavorites();
	const favSelectedId = useUIStore((s) => s.favSelectedId);
	const setFavSelectedId = useUIStore((s) => s.setFavSelectedId);
	const { data: fragrance, isLoading: loadingFrag } =
		useFragrance(favSelectedId);

	// Client-side search over favorites (name / brand).
	const [q, setQ] = useState("");

	const results = data?.results ?? [];
	const count = data?.count ?? results.length;
	const trained = data?.recommender?.trained ?? false;
	const selectedId = results.some((r) => r.id === favSelectedId)
		? favSelectedId
		: null;

	const needle = q.trim().toLowerCase();
	const filtered = needle
		? results.filter(
				(r) =>
					(r.name ?? "").toLowerCase().includes(needle) ||
					(r.brand ?? "").toLowerCase().includes(needle),
			)
		: results;

	const handleClear = () => {
		if (!window.confirm("Remove ALL favorites?")) return;
		clear.mutate();
	};

	return (
		<RequireAuth>
			<div className="grid h-full grid-cols-[minmax(0,1fr)_340px]">
			<div className="flex min-h-0 flex-col">
				<div className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-card px-3">
					<span className="text-xs text-muted-foreground">
						<span className="font-semibold text-foreground">{fmt(count)}</span>{" "}
						favorite{count === 1 ? "" : "s"}
					</span>
					<span className="hidden text-xs text-muted-foreground sm:inline">
						{trained
							? "sorted by most likely to be my favorite"
							: "sorted by most recent (training…)"}
					</span>
					<div className="relative ml-auto w-52">
						<Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
						<DebouncedTextInput
							value={q}
							onCommit={setQ}
							placeholder="Search favorites…"
							className="h-7 pl-7 text-xs"
						/>
					</div>
					<Button
						variant="outline"
						size="sm"
						className="h-7 px-2 text-xs text-dislike hover:text-dislike"
						disabled={count === 0 || clear.isPending}
						onClick={handleClear}
					>
						{clear.isPending ? "Clearing…" : "Clear all"}
					</Button>
				</div>

				<div className="min-h-0 flex-1 overflow-y-auto p-3">
					{isLoading ? (
						<div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
							{Array.from({ length: 8 }).map((_, i) => (
								<div
									key={i}
									className="flex flex-col gap-1.5 rounded-lg border border-border p-2"
								>
									<Skeleton className="h-[150px] w-full" />
									<Skeleton className="h-3 w-3/4" />
									<Skeleton className="h-2.5 w-1/2" />
								</div>
							))}
						</div>
					) : isError ? (
						<div className="flex h-full items-center justify-center text-sm text-muted-foreground">
							Error loading favorites.
						</div>
					) : !results.length ? (
						<div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
							<span>No favorites yet</span>
							<span className="text-xs text-muted-foreground/60">
								Tap ☆ on any fragrance to save it here.
							</span>
						</div>
					) : !filtered.length ? (
						<div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
							<span>No favorites match “{q}”.</span>
							<span className="text-xs text-muted-foreground/60">
								Try a different name or brand.
							</span>
						</div>
					) : (
						<div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
							{filtered.map((r) => (
								<FragranceCard
									key={r.id}
									fragrance={r}
									selected={selectedId === r.id}
									onOpen={setFavSelectedId}
									badge={
										r.p != null ? (
											<span
												title={`Recommender match: ${Math.round(r.p * 100)}%`}
											>
												{Math.round(r.p * 100)}% match
											</span>
										) : undefined
									}
								/>
							))}
						</div>
					)}
				</div>
			</div>

			<div className="min-h-0 overflow-y-auto border-l border-border">
				{selectedId == null ? (
					<div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
						<span>Select a favorite</span>
						<span className="text-xs text-muted-foreground/60">
							Click any square to view details
						</span>
					</div>
				) : loadingFrag || !fragrance ? (
					<div className="flex flex-col gap-2 p-4">
						<Skeleton className="h-4 w-3/4" />
						<Skeleton className="h-3 w-1/3" />
						<Skeleton className="mt-3 h-8 w-full" />
						<Skeleton className="h-24 w-full" />
					</div>
				) : (
					<FragranceDetail fragrance={fragrance} />
				)}
			</div>
		</div>
		</RequireAuth>
	);
}
