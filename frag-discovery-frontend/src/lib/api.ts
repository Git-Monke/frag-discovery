import type {
	AuthResponse,
	FavoriteToggleResponse,
	FavoritesResponse,
	FavoritesSort,
	FeedbackAction,
	Fragrance,
	IngredientStats,
	NoteImages,
	RecommendResponse,
	SearchParams,
	SearchResponse,
	Stats,
	UserOut,
} from "@/lib/types";
import { getAuthToken } from "@/lib/token";

async function request<T>(
	url: string,
	init?: RequestInit,
	token?: string | null,
): Promise<T> {
	// Attach the signed-in user's bearer token to every request so the per-user
	// endpoints (favorites/recommend/feedback/fragrance) work. Catalog endpoints
	// still on the reference backend simply ignore the header.
	const authToken = token ?? getAuthToken();
	let res: Response;
	try {
		res = await fetch(url, {
			...init,
			headers: {
				...(init?.headers ?? {}),
				...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
			},
		});
	} catch {
		throw new Error(`Network error fetching ${url}`);
	}
	if (!res.ok) {
		throw new Error(`API ${res.status}: ${res.statusText}`);
	}
	if (res.status === 204) {
		return undefined as T;
	}
	return res.json() as Promise<T>;
}

export function toSearchParams(params: SearchParams): URLSearchParams {
	const p = new URLSearchParams();
	const set = (key: string, val: unknown) => {
		if (val === undefined || val === null || val === "") return;
		p.set(key, String(val));
	};
	set("q", params.q);
	set("brand", params.brand);
	set("year_min", params.year_min);
	set("year_max", params.year_max);
	set("rating_min", params.rating_min);
	set("rating_max", params.rating_max);
	set("votes_min", params.votes_min);
	set("votes_max", params.votes_max);
	if (params.longevity) {
		p.set("longevity", params.longevity);
		if (params.longevity_min) p.set("longevity_min", "1");
	}
	if (params.sillage) {
		p.set("sillage", params.sillage);
		if (params.sillage_min) p.set("sillage_min", "1");
	}
	set("season", params.season);
	set("gender", params.gender);
	if (params.available) p.set("available", "1");
	if (params.conditions?.length)
		p.set("conditions", JSON.stringify(params.conditions));
	// Browse is a recommender-first app: always rank by the taste model.
	// When the model isn't trained yet the backend falls back to Bayesian.
	set("sort", "recommended");
	set("order", params.order ?? "desc");
	set("page", params.page ?? 1);
	set("page_size", params.page_size ?? 25);
	return p;
}

export const api = {
	search(params: SearchParams): Promise<SearchResponse> {
		return request<SearchResponse>(
			`/api/search?${toSearchParams(params).toString()}`,
		);
	},
	fragrance(id: number): Promise<Fragrance> {
		return request<Fragrance>(`/api/fragrance/${id}`);
	},
	stats(): Promise<Stats> {
		return request<Stats>("/api/stats");
	},
	notes(): Promise<NoteImages> {
		return request<NoteImages>("/api/notes");
	},
	ingredientStats(): Promise<IngredientStats> {
		return request<IngredientStats>("/api/ingredient-stats");
	},
	favorites(sort: FavoritesSort = "recent"): Promise<FavoritesResponse> {
		return request<FavoritesResponse>(
			`/api/favorites${sort === "recommend" ? "?sort=recommend" : ""}`,
		);
	},
	clearFavorites(): Promise<{ count: number }> {
		return request<{ count: number }>("/api/favorites", { method: "DELETE" });
	},
	/** Toggle a favorite. `on` is the target state: true = favorite it. */
	toggleFavorite(id: number, on: boolean): Promise<FavoriteToggleResponse> {
		return request<FavoriteToggleResponse>(`/api/favorites/${id}`, {
			method: on ? "POST" : "DELETE",
		});
	},
	/** Next batch of personalized recommendations. */
	recommend(limit = 10): Promise<RecommendResponse> {
		return request<RecommendResponse>(`/api/recommend?limit=${limit}`);
	},
	/** Record a taste rating on a fragrance — trains the recommender.
	 *  action: pass (-1.0) | interested (+1.0) | love (+2.0, also favorites
	 *  the fragrance). */
	feedback(id: number, action: FeedbackAction): Promise<{ ok: boolean }> {
		return request<{ ok: boolean }>(`/api/feedback/${id}`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ action }),
		});
	},
	/** Remove a rating (undo); also removes the favorite if it was a love. */
	removeFeedback(id: number): Promise<{ ok: boolean }> {
		return request<{ ok: boolean }>(`/api/feedback/${id}`, {
			method: "DELETE",
		});
	},
	auth: {
		/** Exchange a Google ID token for a backend bearer session. */
		google(idToken: string): Promise<AuthResponse> {
			return request<AuthResponse>("/api/auth/google", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ id_token: idToken }),
			});
		},
		/** Fetch the current user profile for a bearer token. 401 = invalid/expired. */
		me(token: string): Promise<UserOut> {
			return request<UserOut>("/api/auth/me", {}, token);
		},
		/** Revoke the session (204 on success). */
		logout(token: string): Promise<void> {
			return request<void>("/api/auth/logout", { method: "POST" }, token);
		},
	},
};
