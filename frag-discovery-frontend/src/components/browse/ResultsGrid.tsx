import type { ReactNode } from "react";
import { FavoriteButton } from "@/components/common/FavoriteButton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { useUIStore } from "@/stores/ui";
import { avif, fmtBayes } from "@/lib/utils";
import type { FragranceRow } from "@/lib/types";
import { cn } from "@/lib/utils";

export function FragranceCard({
	fragrance: r,
	selected,
	onOpen,
	badge,
}: {
	fragrance: FragranceRow;
	selected: boolean;
	onOpen: (id: number) => void;
	/** Optional overlay badge (e.g. a similarity %) rendered over the image. */
	badge?: ReactNode;
}) {
	return (
		<div
			className={cn(
				"group relative flex cursor-pointer flex-col overflow-hidden rounded-lg border bg-card transition-colors",
				selected ? "border-primary" : "border-border hover:border-primary/60",
			)}
			onClick={() => onOpen(r.id)}
		>
			<FavoriteButton
				id={r.id}
				favorited={r.favorited}
				className={cn(
					"absolute right-1 z-10 bg-background/60 backdrop-blur-sm",
					badge ? "top-7" : "top-1",
				)}
			/>
			<div className="flex h-[150px] items-center justify-center overflow-hidden bg-background">
				{badge && (
					<span className="absolute top-1 right-1 z-10 rounded-full border border-primary/40 bg-background/80 px-2 py-0.5 text-[10px] font-bold text-primary backdrop-blur-sm">
						{badge}
					</span>
				)}
				<ImageWithFallback
					src={avif(r.image_url)}
					alt={r.name ?? ""}
					fallback={<span className="text-3xl">🧴</span>}
					className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
					loading="lazy"
				/>
			</div>
			<div className="flex flex-1 flex-col gap-0.5 border-t border-border p-2">
				<div
					className="truncate text-[12px] leading-tight font-medium"
					title={r.name ?? ""}
				>
					{r.name ?? "—"}
				</div>
				<div
					className="truncate text-[10px] text-muted-foreground"
					title={r.brand ?? ""}
				>
					{r.brand ?? ""}
				</div>
				<div className="mt-auto pt-1 text-[12px] font-bold text-primary">
					{fmtBayes(r.bayesian_score)}
				</div>
			</div>
		</div>
	);
}

export function ResultsGrid({
	results,
	onOpen,
}: {
	results: FragranceRow[];
	onOpen: (id: number) => void;
}) {
	const selectedId = useUIStore((s) => s.selectedId);
	return (
		<div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3 p-3">
			{results.map((r) => {
				// Top-corner "% match" badge, mirroring the Favorites page: shown on
				// every card once the taste model is trained (recommended_score set).
				const match =
					r.recommended_score != null
						? `${Math.round(r.recommended_score * 100)}% match`
						: undefined;
				return (
					<FragranceCard
						key={r.id}
						fragrance={r}
						selected={selectedId === r.id}
						onOpen={onOpen}
						badge={match}
					/>
				);
			})}
		</div>
	);
}
