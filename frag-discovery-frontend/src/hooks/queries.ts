import { useMemo } from "react";
import {
	useMutation,
	useQuery,
	useQueryClient,
	type QueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
	FavoritesSort,
	FeedbackAction,
	FragranceRow,
	SearchParams,
} from "@/lib/types";
import { useFiltersStore, buildSearchParams } from "@/stores/filters";

// ---- Static-ish data (globals only change when the server restarts) ----
export function useStats() {
	return useQuery({
		queryKey: ["stats"],
		queryFn: api.stats,
		staleTime: Infinity,
	});
}

export function useNotes() {
	return useQuery({
		queryKey: ["notes"],
		queryFn: api.notes,
		staleTime: Infinity,
	});
}

export function useIngredientStats() {
	return useQuery({
		queryKey: ["ingredient-stats"],
		queryFn: api.ingredientStats,
		staleTime: Infinity,
	});
}

// ---- Search / detail / similar ----
export function useSearch(params: SearchParams) {
	return useQuery({
		queryKey: ["search", params],
		queryFn: () => api.search(params),
		// Keep the previous page's results visible while a new page/filter loads.
		placeholderData: (prev) => prev,
	});
}

/** Search driven by the shared filter store (Browse + Discover). */
export function useFilteredSearch(overrides?: Partial<SearchParams>) {
	const state = useFiltersStore();
	const params = useMemo(() => {
		const base = buildSearchParams(state);
		return overrides ? { ...base, ...overrides } : base;
	}, [state, overrides]);
	return useSearch(params);
}

export function useFragrance(id: number | null) {
	return useQuery({
		queryKey: ["fragrance", id],
		queryFn: () => api.fragrance(id as number),
		enabled: id != null,
	});
}

export function useFavorites(sort: FavoritesSort = "recent") {
	return useQuery({
		queryKey: ["favorites", sort],
		queryFn: () => api.favorites(sort),
		// Favorites can change in another tab — refresh on focus so the Discover
		// feed can drop newly-favorited frags from its queue.
		refetchOnWindowFocus: true,
		// Keep the previous list visible while re-ranking (toggling the
		// recommender sort) so the grid doesn't flash empty.
		placeholderData: (prev) => prev,
	});
}

// ---- Recommender feed (Discover) ----

/**
 * Next batch of personalized recommendations. `nonce` is bumped to force a
 * refetch when the local queue runs low.
 */
export function useRecommend(limit = 10, nonce: number) {
	return useQuery({
		queryKey: ["recommend", limit, nonce],
		queryFn: () => api.recommend(limit),
		placeholderData: (prev) => prev,
	});
}

/** Record a taste rating — trains the recommender. Love also favorites the
 *  fragrance (the backend keeps favorites and the love rating in sync), so
 *  the favorites list is refreshed to keep the feed + header counts honest. */
export function useFeedback() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ id, action }: { id: number; action: FeedbackAction }) =>
			api.feedback(id, action),
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: ["favorites"] });
		},
	});
}

/** Undo a rating so the fragrance becomes recommendable again. A love undo
 *  removes the favorite too, so the favorites list is refreshed. */
export function useRemoveFeedback() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (id: number) => api.removeFeedback(id),
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: ["favorites"] });
		},
	});
}

// ---- Favorite toggle (optimistic, mirrors the old global star delegation) ----
interface UpdateResult {
	results?: FragranceRow[];
}
type UnknownRecord = Record<string, unknown> & UpdateResult;

function updateFavoritedInCache(
	queryClient: QueryClient,
	id: number,
	favorited: boolean,
) {
	const patchResults = (old: unknown) => {
		if (!old || typeof old !== "object") return old;
		const rec = old as UnknownRecord;
		if (!Array.isArray(rec.results)) return old;
		return {
			...rec,
			results: rec.results.map((r) => (r.id === id ? { ...r, favorited } : r)),
		};
	};
	// Search + similar responses carry { results: [...] } with favorited flags.
	queryClient.setQueriesData({ queryKey: ["search"] }, patchResults);
	queryClient.setQueriesData({ queryKey: ["similar"] }, patchResults);
	// The detail row for this fragrance has a favorited flag too.
	queryClient.setQueriesData(
		{ queryKey: ["fragrance", id] },
		(old: unknown) => {
			if (!old || typeof old !== "object") return old;
			const rec = old as UnknownRecord;
			if (rec.id !== id) return old;
			return { ...rec, favorited };
		},
	);
}

export function useFavoriteToggle() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ id, on }: { id: number; on: boolean }) =>
			api.toggleFavorite(id, on),
		onMutate: async ({ id, on }) => {
			await queryClient.cancelQueries({ queryKey: ["favorites"] });
			updateFavoritedInCache(queryClient, id, on);
			return { id, on };
		},
		onError: (_err, vars) => {
			// Roll the optimistic update back.
			updateFavoritedInCache(queryClient, vars.id, !vars.on);
		},
		onSettled: (_data, _err, vars) => {
			// Re-fetch the favorites list so the Favorites page reflects the change.
			queryClient.invalidateQueries({ queryKey: ["favorites"] });
			// Any cache entries we optimistically patched are now authoritative;
			// leave search/similar/fragrance caches as-is.
			void vars;
		},
	});
}

export function useClearFavorites() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: () => api.clearFavorites(),
		onMutate: async () => {
			await queryClient.cancelQueries({ queryKey: ["favorites"] });
			// After a full clear, every cached row is no longer favorited.
			const clearFlags = (old: unknown) => {
				if (!old || typeof old !== "object") return old;
				const rec = old as UpdateResult;
				if (!Array.isArray(rec.results)) return old;
				return {
					...rec,
					results: rec.results.map((r) => ({ ...r, favorited: false })),
				};
			};
			queryClient.setQueriesData({ queryKey: ["search"] }, clearFlags);
			queryClient.setQueriesData({ queryKey: ["similar"] }, clearFlags);
		},
		onSettled: () => {
			queryClient.invalidateQueries({ queryKey: ["favorites"] });
		},
	});
}
