// Type shapes mirroring the Flask API contract in app.py (unchanged backend).

// ---- Vote columns ----
export interface VoteColumns {
	longevity_very_weak?: number | null;
	longevity_weak?: number | null;
	longevity_moderate?: number | null;
	longevity_long_lasting?: number | null;
	longevity_eternal?: number | null;
	sillage_intimate?: number | null;
	sillage_moderate?: number | null;
	sillage_strong?: number | null;
	sillage_enormous?: number | null;
	season_spring?: number | null;
	season_summer?: number | null;
	season_fall?: number | null;
	season_winter?: number | null;
	gender_female?: number | null;
	gender_more_female?: number | null;
	gender_unisex?: number | null;
	gender_more_male?: number | null;
	gender_male?: number | null;
	rating_love?: number | null;
	rating_like?: number | null;
	rating_ok?: number | null;
	rating_dislike?: number | null;
	rating_hate?: number | null;
	time_day?: number | null;
	time_night?: number | null;
	price_way_overpriced?: number | null;
	price_overpriced?: number | null;
	price_ok?: number | null;
	price_good_value?: number | null;
	price_great_value?: number | null;
}

// ---- Fragrance shapes ----
export interface FragranceRow extends VoteColumns {
	id: number;
	name: string | null;
	brand: string | null;
	year: number | null;
	url: string | null;
	rating: number | null;
	votes: number | null;
	image_url: string | null;
	bayesian_score: number | null;
	price_value_score?: number | null;
	love_per_dollar_score?: number | null;
	most_loved_score?: number | null;
	most_liked_score?: number | null;
	controversial_score?: number | null;
	// Personalized: present (0..1) only on "Recommended for you" search results.
	recommended_score?: number | null;
	// Present only if the server sends them (extra table columns); otherwise null.
	liked_score?: number | null;
	loved_score?: number | null;
	friendly_score?: number | null;
	favorited?: boolean;
}

export interface NoteItem {
	name: string;
	strength_pct?: number | null;
	image_url?: string | null;
}

export interface AccordItem {
	name: string;
	strength_pct?: number | null;
}

// Full /api/fragrance/<id> row (SELECT *).
export interface Fragrance extends FragranceRow {
	top_notes_json?: NoteItem[];
	middle_notes_json?: NoteItem[];
	base_notes_json?: NoteItem[];
	accords_json?: AccordItem[];
	availability?: string | null;
	in_production?: number | null;
	shop_count?: number | null;
	featured_price?: string | null;
	price_min?: number | null;
	price_max?: number | null;
	currency?: string | null;
}

// ---- Search ----
export type VoteGroup = "longevity" | "sillage" | "season" | "gender";

export type Longevity =
	| "very_weak"
	| "weak"
	| "moderate"
	| "long_lasting"
	| "eternal";
export type Sillage = "intimate" | "moderate" | "strong" | "enormous";
export type Season =
	| "hot"
	| "cold"
	| "universal"
	| "spring"
	| "summer"
	| "fall"
	| "winter";
export type Gender =
	| "female"
	| "more_female"
	| "female_wearable"
	| "unisex"
	| "male_wearable"
	| "more_male"
	| "male";

export type SortKey =
	| "bayesian"
	| "recommended"
	| "rating"
	| "votes"
	| "loved"
	| "liked"
	| "controversial"
	| "price_value"
	| "love_per_dollar"
	| "year"
	| "name";

export type ConditionType =
	| "accord"
	| "top"
	| "mid"
	| "base"
	| "any_note"
	| "at_least";

export interface NoteCondition {
	type: Exclude<ConditionType, "at_least">;
	name: string;
	min_pct?: number;
	max_pct?: number;
}

export interface AtLeastCondition {
	type: "at_least";
	count: number;
	names: string[];
}

export type Condition = NoteCondition | AtLeastCondition;

/** Conditions as stored client-side: carries a stable React key. */
export type ConditionWithId = Condition & { id: string };

export interface SearchParams {
	q?: string;
	brand?: string;
	year_min?: number;
	year_max?: number;
	rating_min?: number;
	rating_max?: number;
	votes_min?: number;
	votes_max?: number;
	longevity?: Longevity;
	longevity_min?: boolean;
	sillage?: Sillage;
	sillage_min?: boolean;
	season?: Season;
	gender?: Gender;
	available?: boolean;
	conditions?: Condition[];
	sort?: SortKey;
	order?: "asc" | "desc";
	page?: number;
	page_size?: number;
	random?: boolean;
}

export interface SearchResponse {
	total: number;
	page: number;
	page_size: number;
	pages: number;
	results: FragranceRow[];
	// True only when sort=recommended and the taste model was actually trained.
	recommended_trained?: boolean;
}

// ---- Stats / ingredients ----
export interface NoteStat {
	name: string;
	total: number;
	top: number;
	mid: number;
	base: number;
	image_url?: string | null;
}

export interface AccordStat {
	name: string;
	count: number;
	avg_strength?: number | null;
}

export interface Stats {
	mean_rating: number;
	median_votes: number;
	total_count: number;
	brand_list: string[];
	mean_price_value: number;
	median_price_votes: number;
	mean_liked: number;
	note_stats: NoteStat[];
	accord_stats: AccordStat[];
}

export interface IngredientStats {
	notes: NoteStat[];
	accords: AccordStat[];
}

export type NoteImages = Record<string, string>;

// ---- Favorites ----
export interface FavoriteRow extends FragranceRow {
	/** Predicted P(favorite) from the recommender; null when not trained. */
	p?: number | null;
}

export type FavoritesSort = "recent" | "recommend";

// ---- Taste scale (Discover feed + recommender training) ----
export type FeedbackAction = "pass" | "interested" | "love";

/**
 * Training weight per rating level, on the 3-level scale:
 * "Pass" (-1, not interested in trying — like or unsure don't matter, the
 * outcome is the same) / "Interested" (+1, I'd like to try it) / "Love"
 * (+2, the favorite). Anything rated "love" is ALSO added to favorites;
 * every other level is logged for the recommender to train on.
 * Mirrors FEEDBACK_WEIGHTS in app.py (RECO_LEVELS=3).
 */
export const FEEDBACK_WEIGHTS: Record<FeedbackAction, number> = {
	pass: -1.0,
	interested: 1.0,
	love: 2.0,
};

export interface FeedbackLevels {
	pass: number;
	interested: number;
	love: number;
}

export interface FavoritesRecommender {
	/** True when the LR model was trained (>= REC_MIN_FAVORITES positive signals). */
	trained: boolean;
	favorites: number;
	/** Logged ratings per level (user_feedback rows). */
	levels: FeedbackLevels;
	sort: FavoritesSort;
}

export interface FavoritesResponse {
	count: number;
	results: FavoriteRow[];
	recommender?: FavoritesRecommender;
}

export interface FavoriteToggleResponse {
	favorited: boolean;
}

// ---- Recommender (Discover feed) ----
export interface RecommendResult extends FragranceRow {
	/** Predicted P(favorite); null for exploration / cold-start picks. */
	p: number | null;
	exploration: boolean;
}

export interface RecommendProfile {
	favorites: number;
	/** Logged ratings per level (user_feedback rows). */
	levels: FeedbackLevels;
	/** Total user decisions (favorites ∪ rated frags) — drives explore-rate decay. */
	swipes: number;
	cold_start: boolean;
}

export interface RecommendResponse {
	profile: RecommendProfile;
	explore_rate: number;
	results: RecommendResult[];
}

// ---- Auth (Google sign-in, new backend /api/auth/*) ----
export interface UserOut {
	id: number;
	email: string;
	name: string | null;
	picture: string | null;
	created_at: string;
}

export interface AuthResponse {
	access_token: string;
	token_type: string;
	expires_in: number;
	user: UserOut;
}
