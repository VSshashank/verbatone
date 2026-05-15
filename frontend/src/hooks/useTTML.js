import { useEffect, useMemo, useState } from "react";

function timeToSeconds(value) {
  if (!value) return 0;
  const parts = value.split(":");
  if (parts.length !== 3) return Number(value) || 0;
  const [hours, minutes, seconds] = parts.map(Number);
  return hours * 3600 + minutes * 60 + seconds;
}

function findActiveWordIndex(words, currentTime) {
  if (!words.length) return -1;

  const exactIndex = words.findIndex((word, index) => {
    const start = word.visualStart ?? word.start;
    const end = word.visualEnd ?? word.end;
    const isLast = index === words.length - 1;
    return currentTime >= start && (isLast ? currentTime <= end : currentTime < end);
  });
  if (exactIndex >= 0) return exactIndex;

  if (currentTime < words[0].start) return -1;

  for (let index = 0; index < words.length - 1; index += 1) {
    const word = words[index];
    const next = words[index + 1];
    if (currentTime > word.end && currentTime < next.start) {
      return word.lineIndex === next.lineIndex ? index : -1;
    }
  }

  const lastWord = words[words.length - 1];
  const lastEnd = lastWord.visualEnd ?? lastWord.end;
  return currentTime > lastEnd && currentTime - lastEnd <= 0.35 ? words.length - 1 : -1;
}

function addVisualTiming(lines) {
  const lyricWords = lines.flatMap((line) => line.words);

  lyricWords.forEach((word, index) => {
    const next = lyricWords[index + 1];
    const minimumEnd = Math.max(word.end, word.start + 0.18);
    let visualEnd = minimumEnd;

    if (next && next.lineIndex === word.lineIndex) {
      visualEnd = Math.max(minimumEnd, next.start);
    } else if (next) {
      const gap = Math.max(next.start - word.end, 0);
      if (gap <= 2.25) {
        visualEnd = Math.max(minimumEnd, Math.min(next.start, word.end + Math.max(0.45, gap * 0.65)));
      } else {
        visualEnd = minimumEnd + 0.75;
      }
    } else {
      visualEnd = minimumEnd + 0.75;
    }

    // Melisma cap — don't keep a word highlighted for more than 1.8s even
    // if the singer holds the note longer.  Matches Apple Music behaviour:
    // highlight on the vocal attack, not for the full held-note duration.
    const maxVisualDuration = 1.8;
    if (visualEnd - word.start > maxVisualDuration) {
      visualEnd = word.start + maxVisualDuration;
    }

    word.visualStart = word.start;
    word.visualEnd = visualEnd;
  });

  return lines.map((line) => {
    if (!line.words.length) return line;
    return {
      ...line,
      visualStart: line.words[0].visualStart ?? line.start,
      visualEnd: line.words[line.words.length - 1].visualEnd ?? line.end,
    };
  });
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
    setLines(addVisualTiming(parsedLines));
  }, [ttmlString]);

  const words = useMemo(() => lines.flatMap((line) => line.words), [lines]);
  const activeIdx = findActiveWordIndex(words, currentTime);
  const activeWord = activeIdx >= 0 ? words[activeIdx] : null;
  const activeLine = lines.find(
    (line) =>
      line.kind === "lyric" &&
      currentTime >= (line.visualStart ?? line.start) &&
      currentTime <= (line.visualEnd ?? line.end),
  );
  const activeLineIdx = activeWord?.lineIndex ?? activeLine?.lineIndex ?? -1;

  const hasPhonetics = useMemo(
    () => words.some((w) => w.phonetic !== null),
    [words],
  );

  return { lines, words, activeIdx, activeLineIdx, activeWord, hasPhonetics };
}
