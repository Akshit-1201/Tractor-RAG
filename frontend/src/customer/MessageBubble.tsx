import { FileIcon, ImageIcon, UserIcon, WrenchIcon } from "../components/icons";
import type { ChatMessage } from "./types";

// Conditional rendering driven entirely by the /api/chat response (spec §11.2):
//   answered + image  -> answer text with the reference figure beneath
//   answered, no image -> answer text only — no placeholder, no apology
//   not answered       -> the "not in the manuals" state plainly, no image
// Sources render under answered responses so grounding is visible.

export default function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="turn turn--user">
        <span className="avatar">
          <UserIcon />
        </span>
        <div className="bubble">
          <p className="answer">{message.text}</p>
        </div>
      </div>
    );
  }

  const sourceNames = Array.from(new Set((message.sources ?? []).map((s) => s.name))).filter(
    Boolean,
  );
  const isRefusal = message.is_answered === false && !message.streaming;

  return (
    <div className="turn turn--bot">
      <span className="avatar">
        <WrenchIcon />
      </span>
      <div className="bubble">
        {isRefusal ? (
          <div className="idk">
            <span className="lamp lamp--warn" style={{ marginTop: 6 }} />
            <div className="idk__body">
              <span className="eyebrow">Not in the manuals</span>
              <p className="answer">{message.text}</p>
            </div>
          </div>
        ) : (
          <p className="answer">
            {message.text}
            {message.streaming && <span className="cursor" aria-hidden />}
          </p>
        )}

        {message.is_answered && message.image && (
          <figure className="plate">
            <img
              src={message.image.url}
              alt={message.image.caption ?? "Reference image"}
              onError={(e) => {
                // "no placeholder" philosophy: if the file is gone, hide the figure
                const figure = e.currentTarget.closest("figure");
                if (figure instanceof HTMLElement) figure.style.display = "none";
              }}
            />
            <figcaption>
              <b>FIG.</b>
              {message.image.caption ?? "Reference image"}
            </figcaption>
          </figure>
        )}

        {message.is_answered && sourceNames.length > 0 && (
          <div className="sources">
            {sourceNames.map((name) => {
              const isImage = /\.(png|jpe?g|webp)$/i.test(name);
              return (
                <span className="source" key={name}>
                  {isImage ? <ImageIcon /> : <FileIcon />}
                  {name}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
