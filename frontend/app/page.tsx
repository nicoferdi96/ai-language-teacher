import { EmailForm } from "@/components/EmailForm";
import { Flag } from "@/components/Flag";
import { Greetings } from "@/components/Greetings";
import { Brand } from "@/components/WizardShell";
import { TARGET_LANGUAGES } from "@/lib/languages";

export default function StartPage() {
  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
      </header>
      <section className="landing">
        <Greetings />
        <div className="landing__copy">
          <h1 className="display">Speak a new language, ten minutes at a time.</h1>
          <p className="lead">
            Lumi is a patient voice tutor. It plans every lesson around you, then you just talk.
          </p>
          <EmailForm />
        </div>
      </section>
      <footer className="langbar" aria-label="Languages you can learn">
        <ul>
          {TARGET_LANGUAGES.map((language) => (
            <li key={language.code}>
              <Flag code={language.code} />
              {language.name}
            </li>
          ))}
        </ul>
      </footer>
    </main>
  );
}
