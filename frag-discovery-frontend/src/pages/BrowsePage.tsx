import { FilterSidebar } from "@/components/browse/FilterSidebar";
import { PageNav } from "@/components/browse/PageNav";
import { ResultsGrid } from "@/components/browse/ResultsGrid";
import { ResultsToolbar } from "@/components/browse/ResultsToolbar";
import { FragranceDetail } from "@/components/detail/FragranceDetail";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilteredSearch, useFragrance } from "@/hooks/queries";
import { useUIStore } from "@/stores/ui";

export default function BrowsePage() {
	const search = useFilteredSearch();
	const selectedId = useUIStore((s) => s.selectedId);
	const setSelectedId = useUIStore((s) => s.setSelectedId);
	const { data: fragrance, isLoading: loadingFrag } = useFragrance(selectedId);

	const results = search.data?.results ?? [];

	return (
		<div className="grid h-full grid-cols-[270px_minmax(0,1fr)_340px]">
			<FilterSidebar />

			<div className="flex min-h-0 flex-col">
				<ResultsToolbar />
				{search.data && !search.data.recommended_trained && (
					<div className="border-b border-border bg-accent/40 px-3 py-1.5 text-xs text-muted-foreground">
						<span className="font-semibold text-foreground">
							Recommended for you
						</span>{" "}
						needs a trained taste profile —{" "}
						<span className="underline decoration-dotted underline-offset-2">
							Discover
						</span>{" "}
						a few fragrances (rate them Pass, Interested, or Love) and revisit.
						Showing Bayesian score meanwhile.
					</div>
				)}
				<div className="min-h-0 flex-1 overflow-y-auto">
					{search.isError ? (
						<div className="flex h-full items-center justify-center text-sm text-muted-foreground">
							Error loading results. Is the backend running on :3232?
						</div>
					) : search.isLoading || (search.isFetching && !search.data) ? (
						<ResultsSkeleton />
					) : !results.length ? (
						<div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
							<span>No fragrances match your filters.</span>
							<span className="text-xs text-muted-foreground/60">
								Try widening the criteria.
							</span>
						</div>
					) : (
						<ResultsGrid results={results} onOpen={setSelectedId} />
					)}
				</div>
				<PageNav
					total={search.data?.total ?? 0}
					pages={search.data?.pages ?? 1}
				/>
			</div>

			<div className="min-h-0 overflow-y-auto border-l border-border">
				{selectedId == null ? (
					<div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
						<span>Select a fragrance</span>
						<span className="text-xs text-muted-foreground/60">
							Click any card to view details
						</span>
					</div>
				) : loadingFrag || !fragrance ? (
					<div className="flex flex-col gap-2 p-4">
						<Skeleton className="h-4 w-3/4" />
						<Skeleton className="h-3 w-1/3" />
						<Skeleton className="mt-3 h-8 w-full" />
						<Skeleton className="h-24 w-full" />
						<Skeleton className="h-24 w-full" />
					</div>
				) : (
					<FragranceDetail fragrance={fragrance} />
				)}
			</div>
		</div>
	);
}

function ResultsSkeleton() {
	return (
		<div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3 p-3">
			{Array.from({ length: 12 }).map((_, i) => (
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
	);
}
