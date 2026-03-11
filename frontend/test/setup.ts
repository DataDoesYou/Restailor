import "@testing-library/jest-dom/vitest";

if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
	process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
}

if (!process.env.NEXT_PUBLIC_API_URL) {
	process.env.NEXT_PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
}
