import { NavLink, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useStats } from "@/hooks/queries";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
	{ to: "/", label: "Browse", end: true },
	{ to: "/discover", label: "Discover" },
	{ to: "/favorites", label: "Favorites" },
	{ to: "/account", label: "Account" },
];

export function Header() {
	const { data: stats } = useStats();
	const status = useAuthStore((s) => s.status);
	const user = useAuthStore((s) => s.user);
	const navigate = useNavigate();
	return (
		<header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-card px-5">
			<h1 className="text-[17px] font-semibold tracking-wide text-primary">
				Fragrance Discovery
			</h1>
			<nav className="flex h-full items-stretch">
				{NAV_ITEMS.map((item) => (
					<NavLink
						key={item.to}
						to={item.to}
						end={item.end}
						className={({ isActive }) =>
							cn(
								"flex items-center border-b-2 px-3.5 text-[13px] transition-colors",
								isActive
									? "border-primary text-primary"
									: "border-transparent text-muted-foreground hover:text-foreground",
							)
						}
					>
						{item.label}
					</NavLink>
				))}
			</nav>
			<div className="ml-auto flex items-center gap-3">
				<span className="text-xs text-muted-foreground">
					{stats
						? `${stats.total_count.toLocaleString()} fragrances · ${stats.brand_list.length.toLocaleString()} brands`
						: "Loading…"}
				</span>
				{status === "authenticated" && user ? (
					<button
						type="button"
						onClick={() => navigate("/account")}
						className="flex cursor-pointer items-center gap-2 rounded-full border border-border bg-muted/40 py-0.5 pr-2.5 pl-0.5 text-xs transition-colors hover:bg-muted/70"
						title="Account"
					>
						{user.picture ? (
							<img
								src={user.picture}
								alt=""
								className="size-5 rounded-full"
							/>
						) : (
							<span className="flex size-5 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-background uppercase">
								{(user.name ?? user.email)[0]}
							</span>
						)}
						<span className="max-w-28 truncate font-medium text-foreground">
							{user.name ?? user.email}
						</span>
					</button>
				) : (
					status === "unauthenticated" && (
						<Button
							variant="outline"
							size="sm"
							className="h-7 px-2.5 text-xs"
							onClick={() => navigate("/account")}
						>
							Sign in
						</Button>
					)
				)}
			</div>
		</header>
	);
}
