/** A language the tutor can teach (each backed by Gradium speech). */
export type TargetLanguage = {
  code: "en" | "es" | "de" | "fr";
  name: string;
  nativeName: string;
  flag: string;
  hello: string;
};

export const TARGET_LANGUAGES: readonly TargetLanguage[] = [
  { code: "es", name: "Spanish", nativeName: "Español", flag: "🇪🇸", hello: "¡Hola!" },
  { code: "fr", name: "French", nativeName: "Français", flag: "🇫🇷", hello: "Bonjour !" },
  { code: "de", name: "German", nativeName: "Deutsch", flag: "🇩🇪", hello: "Hallo!" },
  { code: "en", name: "English", nativeName: "English", flag: "🇬🇧", hello: "Hello!" },
];

/** Common native languages offered in the picker; any other can be typed. */
export const NATIVE_LANGUAGES: readonly string[] = [
  "English",
  "Spanish",
  "Italian",
  "French",
  "German",
  "Portuguese",
  "Dutch",
  "Polish",
  "Romanian",
  "Arabic",
  "Hindi",
  "Chinese",
  "Japanese",
  "Turkish",
];

/** Return the target language for a code, or undefined if unsupported. */
export function findTargetLanguage(code: string | null | undefined): TargetLanguage | undefined {
  return TARGET_LANGUAGES.find((language) => language.code === code);
}
