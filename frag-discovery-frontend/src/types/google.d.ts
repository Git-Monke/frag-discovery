// Minimal ambient types for Google Identity Services (`accounts.google.com/gsi/client`).
// Only the pieces the app uses are declared.

declare global {
	interface Window {
		google?: {
			accounts: {
				id: GsiIdService;
			};
		};
	}
}

interface GsiIdService {
	initialize(config: GsiInitializeConfig): void;
	renderButton(element: Element, options: GsiButtonOptions): void;
	prompt(callback?: (notification: GsiPromptNotification) => void): void;
}

interface GsiInitializeConfig {
	client_id: string;
	callback: (response: GsiCredentialResponse) => void;
	ux_mode?: "popup" | "redirect";
	auto_select?: boolean;
}

interface GsiCredentialResponse {
	credential: string;
	select_by?: string;
}

interface GsiButtonOptions {
	theme?: "outline" | "filled_blue" | "filled_black";
	size?: "large" | "medium" | "small";
	shape?: "rectangular" | "pill";
	text?: "signin_with" | "signup_with" | "continue_with" | "signin";
	width?: number;
	logo_alignment?: "left" | "center";
}

interface GsiPromptNotification {
	isNotDisplayed: () => boolean;
}

export {};