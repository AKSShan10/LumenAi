// "Karim Hasan" -> "KH", "Rafi" -> "R": the round avatar in the call (we show no photos of candidates)
export function initials(name) {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[words.length - 1][0] : words[0]?.[0] || "?").toUpperCase();
}
