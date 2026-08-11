import { Shuffle, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { useFavorites } from "@/hooks/queries";
import { useAuthStore } from "@/stores/auth";
import { fmt } from "@/lib/utils";
import type { FeedbackLevels, FavoritesRecommender } from "@/lib/types";

/**
 * Account page. Shows the signed-in Google profile (or a sign-in prompt) plus
 * the profile signals the recommender is built from (favorites + ratings).
 */
export default function AccountPage() {
	const { data, isLoading } = useFavorites("recommend");
	const status = useAuthStore((s) => s.status);
	const user = useAuthStore((s) => s.user);
	const logout = useAuthStore((s) => s.logout);
	const recommender: FavoritesRecommender | undefined = data?.recommender;
	const levels: FeedbackLevels | undefined = recommender?.levels;
	const favCount = data?.count ?? 0;
	const rated =
		(levels?.pass ?? 0) + (levels?.interested ?? 0) + (levels?.love ?? 0);

	return (
		<div className="mx-auto flex h-full max-w-xl flex-col gap-4 overflow-y-auto p-6">
			<h1 className="text-lg font-semibold">Account</h1>

			{status === "loading" ? (
				<div className="rounded-lg border border-border bg-card p-4">
					<Skeleton className="h-12 w-full" />
				</div>
			) : status === "authenticated" && user ? (
				<div className="rounded-lg border border-border bg-card p-4">
					<div className="flex items-center gap-3">
						{user.picture ? (
							<img
								src={user.picture}
								alt=""
								className="size-12 shrink-0 rounded-full"
							/>
						) : (
							<span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-semibold text-background uppercase">
								{(user.name ?? user.email)[0]}
							</span>
						)}
						<div className="min-w-0 flex-1">
							<div className="truncate font-semibold">
								{user.name ?? "Account"}
							</div>
							<div className="truncate text-xs text-muted-foreground">
								{user.email}
							</div>
						</div>
						<Button
							variant="outline"
							size="sm"
							className="h-7 px-2.5 text-xs"
							onClick={() => void logout()}
						>
							Sign out
						</Button>
					</div>
				</div>
			) : (
				<div className="rounded-lg border border-border bg-card p-4 text-sm">
					<div className="mb-1 text-base font-semibold">
						Sign in to sync your account
					</div>
					<p className="mb-3 text-xs text-muted-foreground">
						Sign in with Google to rate fragrances, build your favorites, and
						train your personalized recommendations.
					</p>
					<GoogleSignInButton />
				</div>
			)}

			<div className="rounded-lg border border-border bg-card p-4 text-sm">
				<div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
					<Shuffle className="size-3.5" />
					<span className="font-medium text-foreground">Taste profile</span>
					{recommender && (
						<span
							className={
								recommender.trained
									? "rounded-full border border-like/40 bg-like/10 px-2 py-0.5 text-[10px] font-semibold text-like"
									: "rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground"
							}
						>
							{recommender.trained ? "trained" : "training"}
						</span>
					)}
				</div>

				{isLoading ? (
					<div className="flex flex-col gap-2">
						<Skeleton className="h-4 w-1/2" />
						<Skeleton className="h-4 w-2/3" />
					</div>
				) : (
					<div className="flex flex-wrap gap-6">
						<Stat
							label="Favorites"
							value={fmt(favCount)}
							icon={<Star className="size-4 text-primary" />}
						/>
						<Stat label="Ratings" value={fmt(rated)} />
						<Stat label="Loved" value={fmt(levels?.love ?? 0)} />
						<Stat label="Interested" value={fmt(levels?.interested ?? 0)} />
						<Stat label="Passed" value={fmt(levels?.pass ?? 0)} />
					</div>
				)}

				{!recommender?.trained && (
					<p className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
						Rate a few fragrances in{" "}
						<span className="font-semibold text-foreground">Discover</span> to
						train your personalised recommendations.
					</p>
				)}
			</div>

			<div className="flex justify-end">
				<Button
					variant="outline"
					size="sm"
					className="text-xs"
					disabled
					title="Not available on the reference backend"
				>
					Reset taste model
				</Button>
			</div>
		</div>
	);
}

function Stat({
	label,
	value,
	icon,
}: {
	label: string;
	value: string;
	icon?: React.ReactNode;
}) {
	return (
		<div className="flex flex-col gap-0.5">
			{icon}
			<span className="text-[10px] tracking-wider text-muted-foreground uppercase">
				{label}
			</span>
			<span className="text-lg font-bold">{value}</span>
		</div>
	);
}
