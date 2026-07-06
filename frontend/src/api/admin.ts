import { api, authHeader } from "./client";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UploadAccepted {
  id: number;
  filename: string;
  status: string;
}

export interface DocumentItem {
  id: number;
  filename: string;
  status: string;
  chunk_count: number;
  uploaded_at: string;
}

export interface ImageItem {
  id: number;
  filename: string;
  status: string;
  category: string | null;
  image_url: string;
  description: string | null;
  uploaded_at: string;
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return api<TokenResponse>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export const listDocuments = () =>
  api<DocumentItem[]>("/admin/documents", { headers: authHeader() });

export function uploadDocument(file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  return api<UploadAccepted>("/admin/documents", {
    method: "POST",
    body: form,
    headers: authHeader(),
  });
}

export const deleteDocument = (id: number) =>
  api<void>(`/admin/documents/${id}`, { method: "DELETE", headers: authHeader() });

export const listImages = () => api<ImageItem[]>("/admin/images", { headers: authHeader() });

export function uploadImage(file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  return api<UploadAccepted>("/admin/images", {
    method: "POST",
    body: form,
    headers: authHeader(),
  });
}

export const deleteImage = (id: number) =>
  api<void>(`/admin/images/${id}`, { method: "DELETE", headers: authHeader() });

export interface TopicCount {
  topic: string;
  count: number;
}

export interface RecentQuestion {
  question: string;
  is_answered: boolean;
  created_at: string;
}

export interface AnalyticsData {
  total_questions: number;
  answered: number;
  unknown: number;
  answer_rate: number;
  top_topics: TopicCount[];
  recent_questions: RecentQuestion[];
}

export const getAnalytics = () =>
  api<AnalyticsData>("/admin/analytics", { headers: authHeader() });
