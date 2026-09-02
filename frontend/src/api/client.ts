import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

let isRefreshing = false;
const failedRequests: Array<{
  resolve: (value: string) => void;
  reject: (reason?: unknown) => void;
}> = [];

const handleRetries = (access_token: string) => {
  failedRequests.forEach(({ resolve }) => resolve(access_token));
  failedRequests.length = 0;
};

const retryFailedRequests = async (originalRequest: any) => {
  try {
    const refreshedToken = await new Promise<string>((resolve, reject) => {
      failedRequests.push({ resolve, reject });
    });
    originalRequest.headers.Authorization = `Bearer ${refreshedToken}`;
    return client(originalRequest);
  } catch (error) {
    return Promise.reject(error);
  }
};

const refreshAccessToken = async (refreshToken: string) => {
  const response = await client.post("/auth/refresh", { refresh_token: refreshToken });
  const { access_token, expires_in } = response.data;
  localStorage.setItem("access_token", access_token);
  localStorage.setItem("access_expires_in", String(expires_in));
  return access_token;
};

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = localStorage.getItem("refresh_token");

      if (refreshToken) {
        originalRequest._retry = true;

        if (isRefreshing) {
          return retryFailedRequests(originalRequest);
        }

        isRefreshing = true;

        try {
          const newToken = await refreshAccessToken(refreshToken);
          handleRetries(newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return client(originalRequest);
        } catch (refreshError) {
          handleRetries("");
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("access_expires_in");
          window.location.href = "/login";
          return Promise.reject(refreshError);
        } finally {
          isRefreshing = false;
        }
      }
    }

    return Promise.reject(error);
  }
);

export default client;
