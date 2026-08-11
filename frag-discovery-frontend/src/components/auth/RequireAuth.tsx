import type { ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Route/content gate: while the auth session is being restored show a
 * skeleton; when signed out show an inline sign-in prompt; otherwise render
 * the guarded content. Used for the Discover and Favorites pages.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
	const status = useAuthStore((s) => s.status);

	if (status === "loading") {
		return (
			<div className="flex h-full flex-col items-center justify-center gap-3 p-6">
				<Skeleton className="h-6 w-44" />
				<Skeleton className="h-4 w-64" />
			</div>
		);
	}

	if (status !== "authenticated") {
		return (
			<div className="flex h-full flex-col items-center justify-center gap-4 p-6">
				<div className="text-lg font-semibold">Sign in to continue</div>
				<p className="max-w-sm text-center text-sm text-muted-foreground">
					Discover and Favorites are tied to your account. Sign in with Google
					to rate fragrances and build your personalized feed.
				</p>
				<GoogleSignInButton className="mt-1" />
			</div>
		);
	}

	return <>{children}</>;
}