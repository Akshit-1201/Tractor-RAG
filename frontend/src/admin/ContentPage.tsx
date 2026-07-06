import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import {
  deleteDocument,
  deleteImage,
  listDocuments,
  listImages,
  uploadDocument,
  uploadImage,
  type DocumentItem,
  type ImageItem,
} from "../api/admin";
import { AlertIcon, FileIcon, ImageIcon, TrashIcon, UploadIcon } from "../components/icons";
import { useAuth } from "../context/AuthContext";
import AdminNav from "./AdminNav";

const STATUS_LABEL: Record<string, { lamp: string; pulse: boolean }> = {
  processing: { lamp: "lamp--warn", pulse: true },
  indexed: { lamp: "lamp--ok", pulse: false },
  failed: { lamp: "lamp--crit", pulse: false },
};

function StatusTag({ status }: { status: string }) {
  const meta = STATUS_LABEL[status] ?? { lamp: "lamp--idle", pulse: false };
  return (
    <span className="status-tag">
      <span className={`lamp ${meta.lamp}${meta.pulse ? " lamp--pulse" : ""}`} />
      {status}
    </span>
  );
}

export default function ContentPage() {
  const { logout } = useAuth();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [docs, imgs] = await Promise.all([listDocuments(), listImages()]);
      setDocuments(docs);
      setImages(imgs);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("API 401")) {
        logout(); // expired token → RequireAuth redirects to login
        return;
      }
      setError("Could not load content. Is the backend running?");
    }
  }, [logout]);

  // poll so 'processing' flips to 'indexed' without a manual reload
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function handleFiles(files: Iterable<File>) {
    setError(null);
    for (const file of files) {
      try {
        if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
          await uploadDocument(file);
        } else if (["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
          await uploadImage(file);
        } else {
          setError(`Unsupported file type: ${file.name} (PDF or PNG/JPEG/WebP only)`);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : `Upload failed for ${file.name}`);
      }
    }
    refresh();
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragOver(false);
    handleFiles(event.dataTransfer.files);
  }

  return (
    <div className="shell">
      <AdminNav active="content" />
      <main className="shell__main">
        <div className="page-head">
          <h1>Reference library</h1>
          <p>Upload the manuals and images the assistant is allowed to answer from.</p>
        </div>

        <div
          className={`dropzone${dragOver ? " dropzone--over" : ""}`}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onDragEnter={() => setDragOver(true)}
          onDragLeave={() => setDragOver(false)}
          onClick={() => fileInput.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInput.current?.click();
          }}
        >
          <span className="dropzone__icon">
            <UploadIcon />
          </span>
          <strong>Drop files here, or click to browse</strong>
          <small>PDF manuals · PNG / JPEG / WebP images</small>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,image/png,image/jpeg,image/webp"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {error && (
          <p className="banner">
            <AlertIcon style={{ width: 18, height: 18, flex: "0 0 auto" }} />
            {error}
          </p>
        )}

        <div className="section-title">
          <h2>Documents</h2>
          <span className="count-pill">{documents.length}</span>
        </div>
        <div className="bay">
          {documents.length === 0 ? (
            <p className="bay__empty">No documents uploaded yet.</p>
          ) : (
            documents.map((doc) => (
              <div className="item" key={doc.id}>
                <span className="item__icon">
                  <FileIcon />
                </span>
                <span className="item__name" title={doc.filename}>
                  {doc.filename}
                </span>
                <span className="item__meta">
                  {doc.status === "indexed" ? `${doc.chunk_count} chunks` : ""}
                </span>
                <StatusTag status={doc.status} />
                <button
                  type="button"
                  className="icon-btn icon-btn--danger"
                  aria-label={`Delete ${doc.filename}`}
                  title="Delete"
                  onClick={() => deleteDocument(doc.id).then(refresh)}
                >
                  <TrashIcon />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="section-title">
          <h2>Reference images</h2>
          <span className="count-pill">{images.length}</span>
        </div>
        <div className="bay">
          {images.length === 0 ? (
            <p className="bay__empty">No images uploaded yet.</p>
          ) : (
            images.map((img) => (
              <div className="item" key={img.id}>
                <span className="item__icon">
                  {img.status === "indexed" ? (
                    <img src={img.image_url} alt={img.filename} />
                  ) : (
                    <ImageIcon />
                  )}
                </span>
                <span className="item__name" title={img.filename}>
                  {img.filename}
                </span>
                <span className="item__meta">{img.category ?? ""}</span>
                <StatusTag status={img.status} />
                <button
                  type="button"
                  className="icon-btn icon-btn--danger"
                  aria-label={`Delete ${img.filename}`}
                  title="Delete"
                  onClick={() => deleteImage(img.id).then(refresh)}
                >
                  <TrashIcon />
                </button>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
