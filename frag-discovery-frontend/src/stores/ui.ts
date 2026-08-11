import { create } from "zustand";
import type { NoteImages } from "@/lib/types";

interface UIState {
	// Selected fragrance in Browse (grid row) → shown in the right detail panel.
	selectedId: number | null;
	// Selected fragrance in the Favorites page's right panel.
	favSelectedId: number | null;
	// Note name → image URL (from /api/notes), used by the note pyramid.
	noteImages: NoteImages;
	// Actions.
	setSelectedId: (id: number | null) => void;
	setFavSelectedId: (id: number | null) => void;
	setNoteImages: (images: NoteImages) => void;
}

export const useUIStore = create<UIState>((set) => ({
	selectedId: null,
	favSelectedId: null,
	noteImages: {},
	setSelectedId: (selectedId) => set({ selectedId }),
	setFavSelectedId: (favSelectedId) => set({ favSelectedId }),
	setNoteImages: (noteImages) => set({ noteImages }),
}));
