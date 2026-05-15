export default function PhoneticLayer({ hasPhonetics, showPhonetics, onToggle }) {
  if (!hasPhonetics) return null;

  return (
    <button
      type="button"
      onClick={onToggle}
      className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition ${
        showPhonetics
          ? "border-amber-400/40 bg-amber-400/10 text-amber-200"
          : "border-zinc-700 bg-transparent text-zinc-400 hover:bg-zinc-800"
      }`}
      title={showPhonetics ? "Hide phonetics" : "Show romanized pronunciation"}
    >
      <span aria-hidden="true">あ→A</span>
      <span>{showPhonetics ? "Phonetics on" : "Phonetics off"}</span>
    </button>
  );
}
