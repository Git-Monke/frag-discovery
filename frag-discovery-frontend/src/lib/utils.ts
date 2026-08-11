import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { FragranceRow, Stats, VoteColumns, VoteGroup } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

// ---- Formatting (ported from templates/index.html) ----
export function fmt(n: number | null | undefined): string {
	if (n == null) return "—";
	return Number(n).toLocaleString();
}

export function fmtRating(n: number | null | undefined): string {
	if (n == null) return "—";
	return Number(n).toFixed(2);
}

export function fmtBayes(n: number | null | undefined): string {
	if (n == null) return "—";
	return Number(n).toFixed(4);
}

export function fmtPct(n: number | null | undefined): string {
	if (n == null) return "—";
	return (Number(n) * 100).toFixed(1) + "%";
}

export function pctOf(
	val: number | null | undefined,
	...group: Array<number | null | undefined>
): number {
	let total = 0;
	for (const v of group) total += v || 0;
	if (!total) return 0;
	return Math.round(((val || 0) / total) * 100);
}

// Dominant vote-group label, e.g. "Long Lasting 42%".
export const DOMINANT_LABELS: Record<
	VoteGroup,
	{ keys: Array<keyof VoteColumns>; labels: string[] }
> = {
	longevity: {
		keys: [
			"longevity_very_weak",
			"longevity_weak",
			"longevity_moderate",
			"longevity_long_lasting",
			"longevity_eternal",
		],
		labels: ["Very Weak", "Weak", "Moderate", "Long Lasting", "Eternal"],
	},
	sillage: {
		keys: [
			"sillage_intimate",
			"sillage_moderate",
			"sillage_strong",
			"sillage_enormous",
		],
		labels: ["Intimate", "Moderate", "Strong", "Enormous"],
	},
	season: {
		keys: ["season_spring", "season_summer", "season_fall", "season_winter"],
		labels: ["Spring", "Summer", "Fall", "Winter"],
	},
	gender: {
		keys: [
			"gender_female",
			"gender_more_female",
			"gender_unisex",
			"gender_more_male",
			"gender_male",
		],
		labels: ["Feminine", "More Fem.", "Unisex", "More Masc.", "Masculine"],
	},
};

export function dominant(row: FragranceRow, group: VoteGroup): string {
	const { keys, labels } = DOMINANT_LABELS[group];
	let maxVal = 0;
	let maxIdx = -1;
	let total = 0;
	keys.forEach((k, i) => {
		const v = row[k] || 0;
		total += v;
		if (v > maxVal) {
			maxVal = v;
			maxIdx = i;
		}
	});
	if (maxIdx < 0 || total === 0) return "—";
	return `${labels[maxIdx]} ${pctOf(maxVal, ...keys.map((k) => row[k]))}%`;
}

// Client-side score computation, mirroring computeScores() in the old app.
// (The server already returns most of these on search rows; this is used when
// a row only has raw vote columns, e.g. favorites.)
export function computeScores(f: FragranceRow, globals?: Stats | null) {
	const C = globals?.mean_rating ?? 3.99;
	const m = globals?.median_votes ?? 61;
	const bayesian =
		(C * m + (f.rating || 0) * (f.votes || 0)) / (m + (f.votes || 0));

	const totalSent =
		(f.rating_love || 0) +
		(f.rating_like || 0) +
		(f.rating_ok || 0) +
		(f.rating_dislike || 0) +
		(f.rating_hate || 0);
	const pLiked =
		totalSent > 0
			? ((f.rating_love || 0) + (f.rating_like || 0)) / totalSent
			: 0;
	const pDisliked =
		totalSent > 0
			? ((f.rating_dislike || 0) + (f.rating_hate || 0)) / totalSent
			: 0;
	const likedScore =
		totalSent > 0
			? (pLiked * (2 * (f.rating_love || 0) + (f.rating_like || 0)) -
					pDisliked * ((f.rating_dislike || 0) + 2 * (f.rating_hate || 0))) /
				totalSent
			: null;
	const lovedScore = totalSent > 0 ? (f.rating_love || 0) / totalSent : null;
	const friendlyScore =
		totalSent + m > 0
			? ((f.rating_love || 0) + (f.rating_like || 0)) / (totalSent + m)
			: null;
	const controversialScore =
		totalSent > 0 ? 2 * Math.min(pLiked, pDisliked) : null;
	return {
		bayesian,
		likedScore,
		lovedScore,
		friendlyScore,
		controversialScore,
		totalSent,
	};
}

// Fragrantica image URLs: the .jpg gets swapped for the dark .avif variant.
export function avif(
	url: string | null | undefined,
): string | null | undefined {
	if (!url) return url;
	return url.replace(/([^/]+)\.jpg$/i, "dark-$1.avif");
}

// Score accessor used by table/detail rendering (server score or fallback).
export function bayesOf(f: FragranceRow, globals?: Stats | null): number {
	return f.bayesian_score ?? computeScores(f, globals).bayesian;
}

// ---- Condensed single-term attributes -------------------------------------
// The user-facing detail/feed shows each of these groups as ONE easy-to-read
// term instead of a full vote breakdown. Rule: include every bucket that
// holds at least CONDENSE_THRESHOLD percent of the group's votes (joined with
// " / "), falling back to the single top bucket when none qualifies. Gender is
// collapsed to Feminine / Unisex / Masculine (the two directional buckets are
// merged into their pole).

// Each bucket also carries a color so the term reads at a glance (a red→green
// or cool→warm ramp per group) — the visual differentiation the old vote bars
// used to provide.

export type CondenseGroup =
	| "longevity"
	| "sillage"
	| "gender"
	| "season"
	| "time"
	| "price";

/** A condensed bucket with its Tailwind text-color class. */
export interface CondensedChip {
	label: string;
	color: string;
}

type Bucket = {
	label: string;
	color: string;
	val: (r: VoteColumns) => number;
};

// Color language reused from the theme palette where it fits the ramp, plus
// a couple of arbitrary tints where a bucket needs its own shade.
const C = {
	love: "text-love", // #e05c5c
	like: "text-like", // #5cb85c
	ok: "text-ok", // #5b8ac7
	dislike: "text-dislike", // #c87c3c
	hate: "text-hate", // #9e4444
	primary: "text-primary", // #d4a84b
	bayesian: "text-bayesian", // #7cb8d4
	teal: "text-[#38d9a9]",
	violet: "text-[#b07ce0]",
	neutral: "text-muted-foreground",
} as const;

const CONDENSE_GROUPS: Record<CondenseGroup, Bucket[]> = {
	longevity: [
		{
			label: "Very Weak",
			color: C.hate,
			val: (r) => r.longevity_very_weak ?? 0,
		},
		{ label: "Weak", color: C.dislike, val: (r) => r.longevity_weak ?? 0 },
		{
			label: "Moderate",
			color: C.primary,
			val: (r) => r.longevity_moderate ?? 0,
		},
		{
			label: "Long Lasting",
			color: C.like,
			val: (r) => r.longevity_long_lasting ?? 0,
		},
		{ label: "Eternal", color: C.teal, val: (r) => r.longevity_eternal ?? 0 },
	],
	sillage: [
		{ label: "Intimate", color: C.hate, val: (r) => r.sillage_intimate ?? 0 },
		{
			label: "Moderate",
			color: C.primary,
			val: (r) => r.sillage_moderate ?? 0,
		},
		{ label: "Strong", color: C.like, val: (r) => r.sillage_strong ?? 0 },
		{
			label: "Enormous",
			color: C.bayesian,
			val: (r) => r.sillage_enormous ?? 0,
		},
	],
	gender: [
		{
			label: "Feminine",
			color: C.love,
			val: (r) => (r.gender_female ?? 0) + (r.gender_more_female ?? 0),
		},
		{ label: "Unisex", color: C.violet, val: (r) => r.gender_unisex ?? 0 },
		{
			label: "Masculine",
			color: C.bayesian,
			val: (r) => (r.gender_male ?? 0) + (r.gender_more_male ?? 0),
		},
	],
	season: [
		{ label: "Spring", color: C.like, val: (r) => r.season_spring ?? 0 },
		{ label: "Summer", color: C.primary, val: (r) => r.season_summer ?? 0 },
		{ label: "Fall", color: C.dislike, val: (r) => r.season_fall ?? 0 },
		{ label: "Winter", color: C.bayesian, val: (r) => r.season_winter ?? 0 },
	],
	time: [
		{ label: "Day", color: C.primary, val: (r) => r.time_day ?? 0 },
		{ label: "Night", color: C.bayesian, val: (r) => r.time_night ?? 0 },
	],
	price: [
		{
			label: "Way Overpriced",
			color: C.hate,
			val: (r) => r.price_way_overpriced ?? 0,
		},
		{
			label: "Overpriced",
			color: C.dislike,
			val: (r) => r.price_overpriced ?? 0,
		},
		{
			label: "Reasonably Priced",
			color: C.neutral,
			val: (r) => r.price_ok ?? 0,
		},
		{ label: "Good Value", color: C.like, val: (r) => r.price_good_value ?? 0 },
		{
			label: "Great Value",
			color: C.teal,
			val: (r) => r.price_great_value ?? 0,
		},
	],
};

/** Percent of the group's votes held by each bucket that clears the bar. */
export const CONDENSE_THRESHOLD = 40;

/**
 * The chosen bucket(s) for an attribute group, each with its color.
 * Gender is already merged to Feminine / Unisex / Masculine by the map above.
 */
export function condensedChips(
	row: VoteColumns,
	group: CondenseGroup,
): CondensedChip[] {
	const buckets = CONDENSE_GROUPS[group];
	const total = buckets.reduce((s, b) => s + b.val(row), 0);
	if (!total) return [];
	const pcts = buckets.map((b) => ({
		label: b.label,
		color: b.color,
		pct: Math.round((b.val(row) / total) * 100),
	}));
	let chosen = pcts.filter((p) => p.pct >= CONDENSE_THRESHOLD);
	if (!chosen.length) {
		const max = Math.max(...pcts.map((p) => p.pct));
		chosen = pcts.filter((p) => p.pct === max);
	}
	return chosen.map((p) => ({ label: p.label, color: p.color }));
}

/**
 * Single-term condensation joined by " / ". E.g.
 *   condensed(f, 'longevity')  -> "Moderate" | "Moderate / Long Lasting" | "—"
 */
export function condensed(row: VoteColumns, group: CondenseGroup): string {
	const chips = condensedChips(row, group);
	return chips.length ? chips.map((c) => c.label).join(" / ") : "—";
}
