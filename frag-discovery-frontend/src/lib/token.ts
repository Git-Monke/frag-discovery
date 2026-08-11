// Module-level bearer token holder. Kept in its own file with no imports so
// the auth store can push the token here and api.request can read it back
// without a circular import (the auth store already imports `api`).
let token: string | null = null;

export function setAuthToken(next: string | null): void {
	token = next;
}

export function getAuthToken(): string | null {
	return token;
}