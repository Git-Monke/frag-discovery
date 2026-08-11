import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/stores/auth";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID: string = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

// initialize() is idempotent but only needs to run once; guard across mounts.
let initialized = false;

// Load the GIS script once and cache the promise so multiple button mounts
// (header, account, gate prompt) share a single <script> tag.
let scriptPromise: Promise<void> | null = null;
function loadGsi(): Promise<void> {
	if (window.google?.accounts) return Promise.resolve();
	if (!scriptPromise) {
		scriptPromise = new Promise((resolve, reject) => {
			const script = document.createElement("script");
			script.src = GIS_SRC;
			script.async = true;
			script.onload = () => resolve();
			script.onerror = () =>
				reject(new Error("Failed to load Google sign-in."));
			document.head.appendChild(script);
		});
	}
	return scriptPromise;
}

/**
 * "Sign in with Google" button (Google Identity Services).
 * Renders nothing until the client ID is configured; surfaces a plain-text
 * error when the script can't load or the sign-in exchange fails.
 */
export function GoogleSignInButton({
	className,
}: {
	className?: string;
}) {
	const ref = useRef<HTMLDivElement>(null);
	const login = useAuthStore((s) => s.login);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!CLIENT_ID) {
			setError("Google sign-in isn't configured (missing VITE_GOOGLE_CLIENT_ID).");
			return;
		}
		let cancelled = false;
		const el = ref.current;
		if (!el) return;

		loadGsi()
			.then(() => {
				if (cancelled || !window.google) return;
				if (!initialized) {
					window.google.accounts.id.initialize({
						client_id: CLIENT_ID,
						ux_mode: "popup",
						callback: async (resp) => {
							try {
								await login(resp.credential);
							} catch {
								setError("Sign-in failed. Please try again.");
							}
						},
					});
					initialized = true;
				}
				window.google.accounts.id.renderButton(el, {
					theme: "outline",
					size: "large",
					shape: "pill",
					text: "continue_with",
					logo_alignment: "left",
				});
			})
			.catch(() => {
				if (!cancelled) setError("Failed to load Google sign-in.");
			});

		return () => {
			cancelled = true;
		};
	}, [login]);

	if (error) {
		return <p className="text-xs text-destructive">{error}</p>;
	}
	return <div ref={ref} className={className} />;
}