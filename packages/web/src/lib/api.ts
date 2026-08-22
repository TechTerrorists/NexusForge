import createClient from "openapi-fetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = createClient({
  baseUrl: API_URL,
  headers: { "Content-Type": "application/json" },
});

export function setAuthToken(token: string) {
  api.use({
    onRequest({ request }) {
      request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  });
}
