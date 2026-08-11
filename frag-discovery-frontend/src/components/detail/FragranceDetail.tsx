import { FavoriteButton } from "@/components/common/FavoriteButton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { BarChart, BarRow } from "@/components/common/ScoreBar";
import { NotePyramid } from "@/components/detail/NotePyramid";
import {
	avif,
	computeScores,
	cn,
	condensedChips,
	fmt,
	fmtBayes,
	fmtRating,
	type CondensedChip,
	type CondenseGroup,
} from "@/lib/utils";
import { useUIStore } from "@/stores/ui";
import type { Fragrance } from "@/lib/types";

interface FragranceDetailProps {
	fragrance: Fragrance;
	/** Hide the ★ toggle (used by Discover, where the feed buttons are the only actions). */
	hideFavoriteButton?: boolean;
	className?: string;
}

function Stat({
	label,
	value,
	className,
}: {
	label: string;
	value: React.ReactNode;
	className?: string;
}) {
	return (
		<div className="flex flex-col gap-0.5">
			<span className="text-[10px] tracking-wider text-muted-foreground uppercase">
				{label}
			</span>
			<span className={cn("text-[15px] font-bold", className)}>{value}</span>
		</div>
	);
}

/** A condensed attribute rendered as one or more colored chips. */
function CondensedStat({
	fragrance,
	label,
	group,
}: {
	fragrance: Fragrance;
	label: string;
	group: CondenseGroup;
}) {
	const chips: CondensedChip[] = condensedChips(fragrance, group);
	return (
		<div className="flex flex-col gap-1">
			<span className="text-[10px] tracking-wider text-muted-foreground uppercase">
				{label}
			</span>
			{chips.length ? (
				<div className="flex flex-wrap gap-1">
					{chips.map((c) => (
						<span
							key={c.label}
							className={cn(
								"rounded-full border border-border bg-background/50 px-2 py-0.5 text-[11px] leading-none font-semibold",
								c.color,
							)}
						>
							{c.label}
						</span>
					))}
				</div>
			) : (
				<span className="text-[13px] text-muted-foreground">—</span>
			)}
		</div>
	);
}

export function FragranceDetail({
	fragrance: f,
	hideFavoriteButton,
	className,
}: FragranceDetailProps) {
	const noteImagesLoaded = useUIStore(
		(s) => Object.keys(s.noteImages).length > 0,
	);
	const { bayesian, totalSent } = computeScores(f);

	const accords = (f.accords_json ?? [])
		.slice()
		.sort((a, b) => (b.strength_pct ?? 0) - (a.strength_pct ?? 0));
	const topNotes = f.top_notes_json ?? [];
	const midNotes = f.middle_notes_json ?? [];
	const baseNotes = f.base_notes_json ?? [];

	return (
		<div className={cn("p-4 text-[13px]", className)}>
			{f.image_url && (
				<ImageWithFallback
					src={avif(f.image_url)}
					alt={f.name ?? ""}
					className="float-right mb-3 ml-3 w-[120px] rounded object-contain"
				/>
			)}

			<div className="flex items-start gap-2">
				<div className="min-w-0 flex-1 text-[15px] font-semibold">
					{f.name ?? "—"}
				</div>
				{!hideFavoriteButton && (
					<FavoriteButton
						id={f.id}
						favorited={f.favorited}
						className="mt-0.5 shrink-0"
					/>
				)}
			</div>
			<div className="mt-0.5 text-xs text-muted-foreground">
				{f.brand ?? ""}
				{f.brand && f.year ? " · " : ""}
				{f.year ?? ""}
			</div>

			<div className="mt-3 grid grid-cols-2 gap-x-2 gap-y-2.5">
				<Stat
					label="Rating"
					value={
						<span>
							{fmtRating(f.rating)}
							<span className="text-[11px] font-normal text-muted-foreground">
								{" "}
								/ 5
							</span>
						</span>
					}
					className="text-primary"
				/>
				<Stat
					label="Votes"
					value={fmt(f.votes)}
					className="text-[13px] text-muted-foreground"
				/>
				<Stat
					label="Bayesian"
					value={fmtBayes(bayesian)}
					className="text-bayesian"
				/>
			</div>

			{/* Condensed single-term attributes — the full vote breakdown stays out
          of the UI; the recommender (and future clients) can read the raw
          columns from the API. Each term is color-coded by bucket. */}
			<div className="mt-3 grid grid-cols-2 gap-x-2 gap-y-2.5 border-t border-border pt-3">
				<CondensedStat fragrance={f} label="Longevity" group="longevity" />
				<CondensedStat fragrance={f} label="Sillage" group="sillage" />
				<CondensedStat fragrance={f} label="Gender" group="gender" />
				<CondensedStat fragrance={f} label="Season" group="season" />
				<CondensedStat fragrance={f} label="Time of Day" group="time" />
				<CondensedStat fragrance={f} label="Price" group="price" />
			</div>

			{(topNotes.length || midNotes.length || baseNotes.length) && (
				<section className="mt-3 border-t border-border pt-3">
					<h3 className="mb-1.5 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
						Notes
					</h3>
					<NotePyramid top={topNotes} middle={midNotes} base={baseNotes} />
					{!noteImagesLoaded && (
						<div className="text-[10px] text-muted-foreground">…</div>
					)}
				</section>
			)}

			{accords.length > 0 && (
				<section className="mt-3 border-t border-border pt-3">
					<h3 className="mb-1.5 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
						Accords
					</h3>
					<BarChart>
						{accords.map((a) => (
							<BarRow
								key={a.name}
								label={a.name}
								value={a.strength_pct}
								total={100}
								colorClass="bg-accord"
								labelClass="min-w-[100px] text-[10px]"
							/>
						))}
					</BarChart>
				</section>
			)}

			{totalSent > 0 && (
				<section className="mt-3 border-t border-border pt-3">
					<h3 className="mb-1.5 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
						Sentiment
					</h3>
					<BarChart>
						<BarRow
							label="Love"
							value={f.rating_love}
							total={totalSent}
							colorClass="bg-love"
						/>
						<BarRow
							label="Like"
							value={f.rating_like}
							total={totalSent}
							colorClass="bg-like"
						/>
						<BarRow
							label="OK"
							value={f.rating_ok}
							total={totalSent}
							colorClass="bg-ok"
						/>
						<BarRow
							label="Dislike"
							value={f.rating_dislike}
							total={totalSent}
							colorClass="bg-dislike"
						/>
						<BarRow
							label="Hate"
							value={f.rating_hate}
							total={totalSent}
							colorClass="bg-hate"
						/>
					</BarChart>
				</section>
			)}
		</div>
	);
}
