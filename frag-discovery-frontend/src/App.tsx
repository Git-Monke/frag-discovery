import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import BrowsePage from "@/pages/BrowsePage";
import DiscoverPage from "@/pages/DiscoverPage";
import FavoritesPage from "@/pages/FavoritesPage";
import AccountPage from "@/pages/AccountPage";

export default function App() {
	return (
		<Routes>
			<Route element={<AppLayout />}>
				<Route index element={<BrowsePage />} />
				<Route path="discover" element={<DiscoverPage />} />
				<Route path="favorites" element={<FavoritesPage />} />
				<Route path="account" element={<AccountPage />} />
				<Route path="*" element={<Navigate to="/" replace />} />
			</Route>
		</Routes>
	);
}
