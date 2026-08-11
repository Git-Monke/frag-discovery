import { Search, Sparkles } from "lucide-react";
import { DebouncedTextInput } from "@/components/common/DebouncedTextInput";
import { useFiltersStore } from "@/stores/filters";

/**
 * Browse toolbar. There is intentionally no sort control: this is a
 * recommender app, so the feed is always ranked by "Recommended for you"
 * (the API layer sends sort=recommended; the backend falls back to Bayesian
 * until the taste model is trained). The summary box on the right just
 * states that so the fixed ranking isn't a mystery.
 */
export function ResultsToolbar() {
	const f = useFiltersStore();

	return (
		<div className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
			<div className="relative w-56">
				<Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
				<DebouncedTextInput
					value={f.q}
					onCommit={(v) => f.set({ q: v }, true)}
					placeholder="Quick search…"
					className="h-7 pl-7 text-xs"
				/>
			</div>

			<div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
				<Sparkles className="size-3.5 text-primary" />
				<span className="font-medium text-foreground">Recommended for you</span>
			</div>
		</div>
	);
}
