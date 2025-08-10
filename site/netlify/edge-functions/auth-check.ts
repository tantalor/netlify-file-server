import type { Context } from "netlify:edge";

const VALID_API_KEYS = ["key-1234", "another-secret-key", "my-app-key"];

export default async (request: Request, context: Context) => {
  // 1. Parse the request URI to get the API key
  const url = new URL(request.url);
  const apiKey = url.searchParams.get("api_key");

  // 2. Validate the API key against the hard-coded list
  if (!apiKey || !VALID_API_KEYS.includes(apiKey)) {
    // 3. If the key is invalid, reject the request with a 401 response
    return new Response("Unauthorized: Invalid or missing API key.", {
      status: 401
    });
  }

  console.log(request.url);

  // 4. If the key is valid, allow the request to proceed
  return context.next();
};
