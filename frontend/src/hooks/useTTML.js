import { useEffect, useMemo, useState } from "react";

function timeToSeconds(value) {
  if (!value) return 0;
  const parts = value.split(":");
  if (parts.length !== 3) return Number(value) || 0;
  const [hours, minutes, seconds] = parts.map(Number);
  return hours * 3600 + minutes * 60 + seconds;
}

export function useTTML(ttmlString, currentTime) {
  const [lines, setLines] = useState([]);

  useEffect(() => {
    if (!ttmlString) {
      setLines([]);
      return;
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(ttmlString, "text/xml");
    const parseError = doc.querySelector("parsererror");
    if (parseError) {
      setLines([]);
      return;
    }

    let globalWordIndex = 0;
    const parsedLines = Array.from(doc.getElementsByTagName("p")).map((paragraph, lineIndex) => {
      const wordSpans = Array.from(paragraph.getElementsByTagName("span")).filter(
        (s) => s.hasAttribute("begin"),
      );

      const words = wordSpans.map((span, wordIndex) => {
        // Check for nested spans (phonetics mode)
        const inner = Array.from(span.children);
        const primarySpan = inner.find((s) => s.getAttribute("style") === "default");
        const phoneticSpan = inner.find((s) => s.getAttribute("style") === "phonetic");

        const text = (primarySpan || span).textContent.trim();
        const phonetic = phoneticSpan ? phoneticSpan.textContent.trim() : null;

        const word = {
          id: `${lineIndex}-${wordIndex}`,
          globalIndex: globalWordIndex,
          text,
          phonetic,
          start: timeToSeconds(span.getAttribute("begin")),
          end: timeToSeconds(span.getAttribute("end")),
          lineIndex,
        };
        globalWordIndex += 1;
        return word;
      });

      return {
        id: `line-${lineIndex}`,
        kind: paragraph.getAttribute("data-kind") || "lyric",
        text: paragraph.getAttribute("data-text") || words.map((word) => word.text).join(" "),
        start: timeToSeconds(paragraph.getAttribute("begin")),
        end: timeToSeconds(paragraph.getAttribute("end")),
        words,
        lineIndex,
      };
    });
    setLines(parsedLines);
  }, [ttmlString]);

  const words = useMemo(() => lines.flatMap((line) => line.words), [lines]);
  const activeIdx = words.findIndex(
    (word) => currentTime >= word.start && currentTime <= word.end,
  );
  const activeWord = activeIdx >= 0 ? words[activeIdx] : null;
  const activeLine = lines.find(
    (line) => line.kind === "lyric" && currentTime >= line.start && currentTime <= line.end,
  );
  const activeLineIdx = activeWord?.lineIndex ?? activeLine?.lineIndex ?? -1;

  const hasPhonetics = useMemo(
    () => words.some((w) => w.phonetic !== null),
    [words],
  );

  return { lines, words, activeIdx, activeLineIdx, activeWord, hasPhonetics };
}
