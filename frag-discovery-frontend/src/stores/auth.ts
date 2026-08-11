import { create } from "zustand";
import { api } from "@/lib/api";
import { setAuthToken } from "@/lib/token";
import type { UserOut } from "@/lib/types";

const TOKEN_KEY = "frag.auth.token";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthState {
	token: string | null;
	user: UserOut | null;
	status: AuthStatus;
	/** Exchange a Google ID token for a session and persist it. */
	login: (idToken: string) => Promise<void>;
	/** Restore a persisted session at app start (validate via /api/auth/me). */
	bootstrap: () => Promise<void>;
	/** Call the backend logout, then clear local auth state. */
	logout: () => Promise<void>;
	/** Clear local auth state without a backend call. */
	clear: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
	token: null,
	user: null,
	status: "loading",

	async login(idToken) {
		const { access_token: token, user } = await api.auth.google(idToken);
		localStorage.setItem(TOKEN_KEY, token);
		setAuthToken(token);
		set({ token, user, status: "authenticated" });
	},

	async bootstrap() {
		const token = localStorage.getItem(TOKEN_KEY);
		if (!token) {
			setAuthToken(null);
			set({ token: null, user: null, status: "unauthenticated" });
			return;
		}
		try {
			const user = await api.auth.me(token);
			setAuthToken(token);
			set({ token, user, status: "authenticated" });
		} catch {
			// Token missing/expired — drop it and sign out.
			localStorage.removeItem(TOKEN_KEY);
			setAuthToken(null);
			set({ token: null, user: null, status: "unauthenticated" });
		}
	},

	async logout() {
		const { token } = get();
		if (token) {
			try {
				await api.auth.logout(token);
			} catch {
				// Ignore network/revoke errors; still clear local state.
			}
		}
		localStorage.removeItem(TOKEN_KEY);
		setAuthToken(null);
		set({ token: null, user: null, status: "unauthenticated" });
	},

	clear() {
		localStorage.removeItem(TOKEN_KEY);
		setAuthToken(null);
		set({ token: null, user: null, status: "unauthenticated" });
	},
}));