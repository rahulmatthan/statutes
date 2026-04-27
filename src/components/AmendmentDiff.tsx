import { useMemo, useState } from "react";
import { diffWords } from "diff";

interface Props {
  before: string;
  after: string;
}

type Mode = "side" | "unified";

export default function AmendmentDiff({ before, after }: Props) {
  const [mode, setMode] = useState<Mode>("side");

  const parts = useMemo(() => diffWords(before, after), [before, after]);

  return (
    <div className="amend-diff" style={{ fontFamily: "var(--font-serif)" }}>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          fontFamily: "var(--font-sans)",
          fontSize: "0.78rem",
          marginBottom: "0.5rem",
        }}
      >
        <button
          type="button"
          onClick={() => setMode("side")}
          aria-pressed={mode === "side"}
          style={btnStyle(mode === "side")}
        >
          Side-by-side
        </button>
        <button
          type="button"
          onClick={() => setMode("unified")}
          aria-pressed={mode === "unified"}
          style={btnStyle(mode === "unified")}
        >
          Unified
        </button>
      </div>
      {mode === "side" ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          <div>
            <div className="amend-label">Before</div>
            <blockquote className="amend-before">
              <p>
                {parts.map((p, i) =>
                  p.added ? null : (
                    <span
                      key={i}
                      style={
                        p.removed
                          ? {
                              background:
                                "color-mix(in oklch, var(--color-amend) 18%, transparent)",
                              textDecoration: "line-through",
                            }
                          : undefined
                      }
                    >
                      {p.value}
                    </span>
                  ),
                )}
              </p>
            </blockquote>
          </div>
          <div>
            <div className="amend-label">After</div>
            <blockquote className="amend-after">
              <p>
                {parts.map((p, i) =>
                  p.removed ? null : (
                    <span
                      key={i}
                      style={
                        p.added
                          ? {
                              background:
                                "color-mix(in oklch, var(--color-accent) 14%, transparent)",
                            }
                          : undefined
                      }
                    >
                      {p.value}
                    </span>
                  ),
                )}
              </p>
            </blockquote>
          </div>
        </div>
      ) : (
        <blockquote className="amend-before">
          <p>
            {parts.map((p, i) => (
              <span
                key={i}
                style={
                  p.added
                    ? {
                        background:
                          "color-mix(in oklch, var(--color-accent) 14%, transparent)",
                      }
                    : p.removed
                      ? {
                          background:
                            "color-mix(in oklch, var(--color-amend) 18%, transparent)",
                          textDecoration: "line-through",
                        }
                      : undefined
                }
              >
                {p.value}
              </span>
            ))}
          </p>
        </blockquote>
      )}
    </div>
  );
}

function btnStyle(active: boolean): React.CSSProperties {
  return {
    padding: "0.2rem 0.6rem",
    border: "1px solid var(--color-rule)",
    borderRadius: 3,
    background: active ? "var(--color-ink)" : "transparent",
    color: active ? "var(--color-paper)" : "var(--color-ink-soft)",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: "inherit",
  };
}
