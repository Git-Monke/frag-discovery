import { create } from "zustand";
import type {
	Condition,
	ConditionWithId,
	Gender,
	Longevity,
	SearchParams,
	Season,
	Sillage,
} from "@/lib/types";

let condCounter = 0;
const tag = (c: Condition): ConditionWithId => ({
	...c,
	id: `cond-${++condCounter}`,
});

function num(v: string): number | undefined {
	if (v === "" || v == null) return undefined;
	const n = Number(v);
	return Number.isFinite(n) ? n : undefined;
}

export interface FiltersState {
	// Filter inputs (strings match the raw input fields).
	q: string;
	brand: string;
	yearMin: string;
	yearMax: string;
	ratingMin: string;
	ratingMax: string;
	votesMin: string;
	votesMax: string;
	longevity: Longevity | "";
	longevityMin: boolean;
	sillage: Sillage | "";
	sillageMin: boolean;
	season: Season | "";
	gender: Gender | "";
	available: boolean;
	conditions: ConditionWithId[];
	// Results controls. Sort is always "recommended for you" (backed into the
	// API layer), so there's no sort/order state here.
	page: number;
	pageSize: number;
	// Actions.
	set: (partial: Partial<FiltersState>, resetPage?: boolean) => void;
	setCondition: (index: number, cond: Condition) => void;
	addCondition: (cond?: Condition) => void;
	removeCondition: (index: number) => void;
	reset: () => void;
}

const initialFilters = {
	q: "",
	brand: "",
	yearMin: "",
	yearMax: "",
	ratingMin: "",
	ratingMax: "",
	votesMin: "",
	votesMax: "",
	longevity: "" as Longevity | "",
	longevityMin: false,
	sillage: "" as Sillage | "",
	sillageMin: false,
	season: "" as Season | "",
	gender: "" as Gender | "",
	available: false,
	conditions: [] as ConditionWithId[],
	page: 1,
	pageSize: 25,
};

export const useFiltersStore = create<FiltersState>((set) => ({
	...initialFilters,
	set: (partial, resetPage = false) =>
		set((s) => ({ ...s, ...partial, ...(resetPage ? { page: 1 } : {}) })),
	setCondition: (index, cond) =>
		set((s) => {
			const conditions = [...s.conditions];
			const prev = conditions[index];
			conditions[index] = { ...cond, id: prev?.id ?? `cond-${++condCounter}` };
			return { conditions };
		}),
	addCondition: (cond) =>
		set((s) => ({
			conditions: [...s.conditions, tag(cond ?? { type: "accord", name: "" })],
		})),
	removeCondition: (index) =>
		set((s) => ({ conditions: s.conditions.filter((_, i) => i !== index) })),
	reset: () =>
		set((s) => ({
			...initialFilters,
			// Keep the page size across a filter reset.
			pageSize: s.pageSize,
		})),
}));

// Derive the API SearchParams from the store. Sort is intentionally omitted:
// the API layer always requests sort=recommended for the browse feed.
export function buildSearchParams(s: FiltersState): SearchParams {
	return {
		q: s.q || undefined,
		brand: s.brand || undefined,
		year_min: num(s.yearMin),
		year_max: num(s.yearMax),
		rating_min: num(s.ratingMin),
		rating_max: num(s.ratingMax),
		votes_min: num(s.votesMin),
		votes_max: num(s.votesMax),
		longevity: s.longevity || undefined,
		longevity_min: s.longevityMin || undefined,
		sillage: s.sillage || undefined,
		sillage_min: s.sillageMin || undefined,
		season: s.season || undefined,
		gender: s.gender || undefined,
		available: s.available || undefined,
		conditions: s.conditions.length ? s.conditions : undefined,
		page: s.page,
		page_size: s.pageSize,
	};
}
