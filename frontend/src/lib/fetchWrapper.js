/**
 * Global fetch wrapper: normalizes network errors and adds retries.
 * This script monkey-patches the global fetch to provide consistent error handling.
 */

const originalFetch = window.fetch;

window.fetch = async (...args) => {
  const MAX_RETRIES = 2;
  let lastError;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await originalFetch(...args);
      
      // If we got a response, return it (even if it's 4xx or 5xx, the app handles those)
      return response;
    } catch (error) {
      lastError = error;
      
      // Only retry on network errors (not 4xx/5xx responses)
      if (attempt < MAX_RETRIES) {
        const delay = Math.pow(2, attempt) * 500;
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
    }
  }

  // If we reached here, it means all retries failed
  console.error('Fetch failed after retries:', lastError);
  throw lastError;
};

console.log('[FetchWrapper] Global fetch wrapper initialized.');
