"use client";

import { useMutation, useQuery } from "@apollo/client";
import { Fraunces, Mulish, Noto_Sans_Tamil, Noto_Serif_Tamil } from "next/font/google";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { setTokens } from "@/lib/auth";
import { GRAPHQL_ENDPOINT } from "@/lib/apollo-client";
import {
  GALLERY_FALLBACK,
  I18N,
  Lang,
  TIMETABLE,
} from "@/lib/landing-content";
import { GALLERY_IMAGES, LOGIN, SITE_LOGO } from "@/lib/graphql/operations";

const fraunces = Fraunces({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-fraunces" });
const mulish = Mulish({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-mulish" });
const notoSerifTamil = Noto_Serif_Tamil({ subsets: ["tamil"], weight: ["400", "500", "600"], variable: "--font-noto-serif-tamil" });
const notoSansTamil = Noto_Sans_Tamil({ subsets: ["tamil"], weight: ["400", "500", "600", "700"], variable: "--font-noto-sans-tamil" });

// Media files are served by Django (same origin as the GraphQL endpoint), so a
// "/media/..." URL must be resolved against that origin, not the Next.js host.
const API_ORIGIN = (() => {
  try {
    return new URL(GRAPHQL_ENDPOINT).origin;
  } catch {
    return "";
  }
})();
function mediaUrl(u: string | null | undefined): string {
  if (!u) return "";
  return u.startsWith("/") ? `${API_ORIGIN}${u}` : u;
}

type GalleryData = { galleryImages: { id: string; imageUrl: string | null; titleEn: string; titleTa: string }[] };
type LogoData = { siteLogo: { id: string; imageUrl: string | null } | null };
type LoginResult = { login: { accessToken: string; refreshToken: string } };

const PhotoIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.4}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="m3 16 5-5 4 4 3-3 6 6" />
    <circle cx="15.5" cy="8.5" r="1.5" />
  </svg>
);

export default function LandingPage() {
  const router = useRouter();
  const [lang, setLang] = useState<Lang>("en");
  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [enquired, setEnquired] = useState(false);
  const [activeDot, setActiveDot] = useState(0);

  const focusRef = useRef<HTMLDivElement>(null);
  const galRef = useRef<HTMLDivElement>(null);

  const t = (key: string) => I18N[lang][key] ?? I18N.en[key] ?? "";

  const { data: galData } = useQuery<GalleryData>(GALLERY_IMAGES, { fetchPolicy: "cache-and-network" });
  const { data: logoData } = useQuery<LogoData>(SITE_LOGO, { fetchPolicy: "cache-and-network" });
  const [login, { loading: loggingIn, error: loginError }] = useMutation<LoginResult>(LOGIN, {
    onCompleted: (d) => {
      setTokens(d.login.accessToken, d.login.refreshToken);
      router.push("/dashboard");
    },
    onError: () => {},
  });

  const galleryItems = galData?.galleryImages ?? [];
  const usingRealPhotos = galleryItems.length > 0;
  const galCount = usingRealPhotos ? galleryItems.length : GALLERY_FALLBACK.length;
  const logoUrl = mediaUrl(logoData?.siteLogo?.imageUrl);

  // Restore the visitor's language choice.
  useEffect(() => {
    try {
      if (localStorage.getItem("nila-lang") === "ta") setLang("ta");
    } catch {
      /* private mode / blocked storage */
    }
  }, []);

  function changeLang(l: Lang) {
    setLang(l);
    try {
      localStorage.setItem("nila-lang", l);
    } catch {
      /* ignore */
    }
  }

  // Gallery: sync dots on scroll + gentle auto-advance (unless reduced-motion).
  useEffect(() => {
    const tr = galRef.current;
    if (!tr) return;
    const slideW = () => {
      const s = tr.querySelector<HTMLElement>(".gslide");
      return s ? s.getBoundingClientRect().width + 16 : 1;
    };
    const onScroll = () => setActiveDot(Math.round(tr.scrollLeft / slideW()));
    tr.addEventListener("scroll", onScroll, { passive: true });
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let timer: ReturnType<typeof setInterval> | undefined;
    if (!reduce && galCount > 1) {
      timer = setInterval(() => {
        const w = slideW();
        const next = (Math.round(tr.scrollLeft / w) + 1) % galCount;
        tr.scrollTo({ left: next * w, behavior: "smooth" });
      }, 5000);
    }
    return () => {
      tr.removeEventListener("scroll", onScroll);
      if (timer) clearInterval(timer);
    };
  }, [galCount]);

  function scrollCar(ref: React.RefObject<HTMLDivElement>, dir: number) {
    const tr = ref.current;
    if (!tr) return;
    const first = tr.querySelector<HTMLElement>(".slide");
    const step = first ? first.getBoundingClientRect().width + 16 : 300;
    tr.scrollBy({ left: dir * step, behavior: "smooth" });
  }

  function scrollToId(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }

  function submitLogin(e: FormEvent) {
    e.preventDefault();
    login({ variables: { email, password } });
  }

  function submitEnquiry(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setEnquired(true);
    e.currentTarget.reset();
  }

  const wrapperClass = [
    fraunces.variable,
    mulish.variable,
    notoSerifTamil.variable,
    notoSansTamil.variable,
    "nila",
    lang === "ta" ? "lang-ta" : "",
  ].join(" ");

  return (
    <div className={wrapperClass} lang={lang}>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      <header>
        <div className="wrap nav">
          <a className="brand" href="#top" onClick={(e) => { e.preventDefault(); scrollToId("top"); }}>
            {logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- served from Django MEDIA; next/image would need remote-host config
              <img className="logo-img" src={logoUrl} alt="Nila Psychiatric Hospital logo" />
            ) : (
              <span className="logo-ph" aria-label="Logo placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <path d="m3 16 5-5 4 4 3-3 6 6" />
                  <circle cx="15.5" cy="8.5" r="1.5" />
                </svg>
                LOGO
              </span>
            )}
            <span className="brand-name">Nila<b>Psychiatric Hospital</b></span>
          </a>
          <nav className="nav-links">
            <a href="#focus">{t("nav.focus")}</a>
            <a href="#services">{t("nav.services")}</a>
            <a href="#gallery">{t("nav.gallery")}</a>
            <a href="#timetable">{t("nav.timetable")}</a>
            <a href="#contact">{t("nav.contact")}</a>
          </nav>
          <div className="nav-right">
            <div className="lang" role="group" aria-label="Language">
              <button className={lang === "en" ? "on" : ""} onClick={() => changeLang("en")}>EN</button>
              <button className={lang === "ta" ? "on" : ""} onClick={() => changeLang("ta")} lang="ta">தமிழ்</button>
            </div>
            <button className="btn btn-gold" onClick={() => setLoginOpen(true)}>{t("nav.login")}</button>
          </div>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="crescent" aria-hidden="true" />
          <div className="wrap">
            <div className="hero-inner">
              <span className="eyebrow">{t("hero.eyebrow")}</span>
              <h1>{t("hero.title")}</h1>
              <p className="lede">{t("hero.lede")}</p>
              <div className="hero-cta">
                <button className="btn btn-gold" onClick={() => scrollToId("contact")}>{t("hero.cta1")}</button>
                <a className="btn btn-ghost-night" href="tel:+917708709960">{t("hero.cta2")} 77087 09960</a>
              </div>
            </div>
          </div>
        </section>

        <section className="stats">
          <div className="wrap">
            <div className="stat"><div className="num">15+</div><div className="lbl">{t("stat.years")}</div></div>
            <div className="stat"><div className="num">3,000+</div><div className="lbl">{t("stat.families")}</div></div>
            <div className="stat"><div className="num">35</div><div className="lbl">{t("stat.trust")}</div></div>
          </div>
        </section>

        <section className="block" id="focus">
          <div className="wrap">
            <div className="car-head">
              <div className="section-head" style={{ marginBottom: 0 }}>
                <span className="eyebrow">{t("focus.eyebrow")}</span>
                <h2>{t("focus.title")}</h2>
              </div>
              <div className="car-nav">
                <button className="car-btn" aria-label="Previous" onClick={() => scrollCar(focusRef, -1)}><Chevron dir="left" /></button>
                <button className="car-btn" aria-label="Next" onClick={() => scrollCar(focusRef, 1)}><Chevron dir="right" /></button>
              </div>
            </div>
            <div className="carousel">
              <div className="track" ref={focusRef}>
                {FOCUS.map((f) => (
                  <div className="focus slide" key={f.key}>
                    <div className="ic">{f.icon}</div>
                    <h3>{t(`${f.key}.t`)}</h3>
                    <p>{t(`${f.key}.d`)}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="block" id="services" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="section-head">
              <span className="eyebrow">{t("services.eyebrow")}</span>
              <h2>{t("services.title")}</h2>
              <p>{t("services.sub")}</p>
            </div>
            <div className="services">
              {SERVICES.map((s) => (
                <div className="service" key={s.key}>
                  <div className="ic">{s.icon}</div>
                  <h3>{t(`${s.key}.t`)}</h3>
                  <p>{t(`${s.key}.d`)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="gallery" id="gallery">
          <div className="wrap block">
            <div className="car-head">
              <div className="section-head" style={{ marginBottom: 0 }}>
                <span className="eyebrow">{t("gallery.eyebrow")}</span>
                <h2 style={{ color: "var(--on-night)" }}>{t("gallery.title")}</h2>
              </div>
              <div className="car-nav">
                <button className="car-btn" aria-label="Previous" onClick={() => scrollCar(galRef, -1)}><Chevron dir="left" /></button>
                <button className="car-btn" aria-label="Next" onClick={() => scrollCar(galRef, 1)}><Chevron dir="right" /></button>
              </div>
            </div>
            <div className="carousel">
              <div className="track" ref={galRef}>
                {usingRealPhotos
                  ? galleryItems.map((g) => (
                      <div
                        className="gslide slide gphoto"
                        key={g.id}
                        style={{ backgroundImage: `url(${mediaUrl(g.imageUrl)})` }}
                      >
                        <div className="cap"><div className="t">{lang === "ta" ? g.titleTa || g.titleEn : g.titleEn}</div></div>
                      </div>
                    ))
                  : GALLERY_FALLBACK.map((g) => (
                      <div className={`gslide slide ${g.cls}`} key={g.cls}>
                        <div className="ph"><PhotoIcon /></div>
                        <div className="cap">
                          <div className="s">{t("g.photo")}</div>
                          <div className="t">{t(g.key)}</div>
                        </div>
                      </div>
                    ))}
              </div>
              <div className="dots">
                {Array.from({ length: galCount }).map((_, i) => (
                  <button
                    key={i}
                    className={i === activeDot ? "on" : ""}
                    aria-label={`Slide ${i + 1}`}
                    onClick={() => {
                      const tr = galRef.current;
                      const s = tr?.querySelector<HTMLElement>(".gslide");
                      if (tr && s) tr.scrollTo({ left: i * (s.getBoundingClientRect().width + 16), behavior: "smooth" });
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="timetable" id="timetable">
          <div className="wrap block">
            <div className="section-head center">
              <span className="eyebrow">{t("tt.eyebrow")}</span>
              <h2>{t("tt.title")}</h2>
              <p>{t("tt.sub")}</p>
            </div>
            <div className="tt-grid">
              {TIMETABLE.map(([time, key]) => (
                <div className="tt-row" key={time}>
                  <span className="time">{time}</span>
                  <span className="act">{t(key)}</span>
                </div>
              ))}
            </div>
            <p className="tt-note">{t("tt.note")}</p>
          </div>
        </section>

        <section className="block" id="about">
          <div className="wrap">
            <div className="about-grid">
              <div>
                <span className="eyebrow">{t("about.eyebrow")}</span>
                <h2>{t("about.title")}</h2>
                <p>{t("about.body")}</p>
              </div>
              <div className="about-card">
                <div className="q">{t("about.quote")}</div>
                <div className="by">{t("about.by")}</div>
              </div>
            </div>
          </div>
        </section>

        <section className="block" id="contact" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="section-head">
              <span className="eyebrow">{t("contact.eyebrow")}</span>
              <h2>{t("contact.title")}</h2>
              <p>{t("contact.sub")}</p>
            </div>
            <div className="contact-grid">
              <div>
                <div className="contact-row">
                  <span className="ic"><IconPhone /></span>
                  <div>
                    <div className="k">{t("contact.call")}</div>
                    <div className="v"><a href="tel:+917708709960">77087 09960</a> · <a href="tel:+917708365220">7708365220</a></div>
                  </div>
                </div>
                <div className="contact-row">
                  <span className="ic"><IconWhatsApp /></span>
                  <div>
                    <div className="k">{t("contact.whatsapp")}</div>
                    <div className="v"><a href="https://wa.me/919677749495">96777 49495</a></div>
                  </div>
                </div>
                <div className="contact-row">
                  <span className="ic"><IconMail /></span>
                  <div>
                    <div className="k">{t("contact.email")}</div>
                    <div className="v"><a href="mailto:nilahealthcare@gmail.com">nilahealthcare@gmail.com</a></div>
                  </div>
                </div>
                <div className="contact-row">
                  <span className="ic"><IconPin /></span>
                  <div>
                    <div className="k">{t("contact.area")}</div>
                    <div className="v" style={{ fontSize: "1rem" }}>{t("contact.areaval")}</div>
                    <div className="socials">
                      <a href="https://facebook.com/nilamindcare" aria-label="Facebook"><IconFacebook /></a>
                      <a href="https://instagram.com/nila.mindcare" aria-label="Instagram"><IconInstagram /></a>
                      <a href="https://wa.me/919677749495" aria-label="WhatsApp"><IconWhatsApp /></a>
                    </div>
                  </div>
                </div>
              </div>
              <form className="enquire" onSubmit={submitEnquiry}>
                <div className="field"><label htmlFor="en-name">{t("form.name")}</label><input id="en-name" required /></div>
                <div className="field"><label htmlFor="en-phone">{t("form.phone")}</label><input id="en-phone" type="tel" required /></div>
                <div className="field"><label htmlFor="en-msg">{t("form.msg")}</label><textarea id="en-msg" rows={3} /></div>
                <button className="btn btn-gold" type="submit" style={{ width: "100%", justifyContent: "center" }}>{t("form.send")}</button>
                {enquired ? <p className="msg ok">{t("form.ok")}</p> : <p className="msg" />}
              </form>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">
          <div className="fbrand">Nila Psychiatric Hospital</div>
          <small>{t("footer.tag")}</small>
          <small>© 2026 Nila Psychiatric Hospital</small>
        </div>
      </footer>

      {loginOpen ? (
        <div className="overlay open" role="dialog" aria-modal="true" aria-labelledby="login-title" onClick={(e) => { if (e.target === e.currentTarget) setLoginOpen(false); }}>
          <div className="modal">
            <div className="modal-head">
              <h3 id="login-title">{t("login.title")}</h3>
              <button className="x" aria-label="Close" onClick={() => setLoginOpen(false)}>✕</button>
            </div>
            <p className="sub">{t("login.sub")}</p>
            <form onSubmit={submitLogin}>
              <div className="field">
                <label htmlFor="lg-email">{t("login.email")}</label>
                <input id="lg-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="lg-pass">{t("login.pass")}</label>
                <input id="lg-pass" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button className="btn btn-gold" type="submit" style={{ width: "100%", justifyContent: "center", marginTop: 4 }} disabled={loggingIn}>
                {loggingIn ? t("login.signingin") : t("login.signin")}
              </button>
              {loginError ? <p className="msg err">{loginError.message}</p> : <p className="msg" />}
            </form>
            <p className="recaptcha-note">{t("login.recaptcha")}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const Chevron = ({ dir }: { dir: "left" | "right" }) => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
    {dir === "left" ? <path d="m15 18-6-6 6-6" /> : <path d="m9 18 6-6-6-6" />}
  </svg>
);

const IconPhone = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2 4.2 2 2 0 0 1 4 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.6a2 2 0 0 1-.5 2.1L8 9.6a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.5c.8.3 1.7.6 2.6.7a2 2 0 0 1 1.7 2z" />
  </svg>
);
const IconMail = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </svg>
);
const IconPin = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);
const IconWhatsApp = () => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2a10 10 0 0 0-8.5 15.3L2 22l4.8-1.3A10 10 0 1 0 12 2zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .1-1.7-.1-.4-.1-.9-.3-1.6-.6-2.8-1.2-4.6-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.8s.7-2 .9-2.2c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 1.9c.1.2.1.3 0 .5-.4.8-.8.9-.5 1.4.6.9 1.2 1.5 2 2 .3.2.5.2.7 0l.7-.9c.2-.3.4-.2.6-.1l1.7.8c.2.1.4.2.4.3.1.2.1.6-.1 1.2z" />
  </svg>
);
const IconFacebook = () => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
    <path d="M13 22v-8h3l.5-3H13V9c0-.9.3-1.5 1.6-1.5H17V5c-.3 0-1.3-.1-2.4-.1C12.3 4.9 11 6.2 11 8.6V11H8v3h3v8z" />
  </svg>
);
const IconInstagram = () => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
    <rect x="3" y="3" width="18" height="18" rx="5" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
  </svg>
);

const FOCUS = [
  { key: "fa.deaddiction", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M5 12h4l2 5 3-10 2 5h3" /></svg> },
  { key: "fa.mood", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="12" r="9" /><path d="M8 15s1.5-2 4-2 4 2 4 2M9 9h.01M15 9h.01" /></svg> },
  { key: "fa.psychosis", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M12 3a4 4 0 0 0-4 4 4 4 0 0 0-1 7.9V17a3 3 0 0 0 6 0M12 3a4 4 0 0 1 4 4 4 4 0 0 1 1 7.9V17a3 3 0 0 1-6 0" /></svg> },
  { key: "fa.geriatric", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg> },
  { key: "fa.counselling", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg> },
  { key: "fa.rehab", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M3 12a9 9 0 1 0 9-9M3 12H1m2 0 3 3" /><path d="M12 7v5l3 2" /></svg> },
];

const SERVICES = [
  { key: "svc.inpatient", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M3 21V9l9-6 9 6v12M9 21v-6h6v6" /></svg> },
  { key: "svc.therapy", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg> },
  { key: "svc.medication", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><rect x="3" y="8" width="18" height="12" rx="3" /><path d="M8 8V6a4 4 0 0 1 8 0v2M12 12v4M10 14h4" /></svg> },
  { key: "svc.nutrition", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M4 4h16v6a8 8 0 0 1-16 0zM8 20h8" /></svg> },
  { key: "svc.aftercare", icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M12 21s-7-4.35-9.5-8.5C.8 9.6 2.5 6 6 6c2 0 3 1.2 4 2.5C11 7.2 12 6 14 6c3.5 0 5.2 3.6 3.5 6.5C19 16.65 12 21 12 21z" /></svg> },
];

const CSS = `
:root {
  --ground:#f7f5f0; --surface:#fff; --surface-2:#efece3;
  --night:#1e2340; --night-2:#262c50;
  --ink:#23263f; --muted:#5c6079; --faint:#8a8ea3;
  --line:#e6e0d4; --line-night:#363c66;
  --gold:#c8893a; --gold-soft:#f2e4cf; --sage:#5f7d73;
  --on-night:#ecebe4; --on-night-muted:#b6b9cf;
  --maxw:1120px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#12152b; --surface:#1b2040; --surface-2:#232949;
    --night:#10132a; --night-2:#1a1f3d;
    --ink:#ecebe4; --muted:#a6aac2; --faint:#7b7f9a;
    --line:#2c3157; --line-night:#2c3157;
    --gold:#e0ac5f; --gold-soft:#33302a; --sage:#8fb0a5;
  }
}
.nila { --font-display: var(--font-fraunces), Georgia, serif; --font-body: var(--font-mulish), system-ui, sans-serif;
  background:var(--ground); color:var(--ink); font-family:var(--font-body); font-size:17px; line-height:1.6;
  -webkit-font-smoothing:antialiased; min-height:100vh; }
.nila.lang-ta { --font-display: var(--font-noto-serif-tamil), serif; --font-body: var(--font-noto-sans-tamil), sans-serif; line-height:1.75; }
.nila *, .nila *::before, .nila *::after { box-sizing:border-box; }
.nila h1, .nila h2, .nila h3 { font-family:var(--font-display); font-weight:500; text-wrap:balance; margin:0; }
.nila p { margin:0; } .nila a { color:inherit; text-decoration:none; }
.nila img { max-width:100%; }
.wrap { max-width:var(--maxw); margin:0 auto; padding-inline:22px; }
.eyebrow { font-size:0.72rem; letter-spacing:0.18em; text-transform:uppercase; font-weight:600; color:var(--gold); }
.nila.lang-ta .eyebrow { letter-spacing:0.05em; }
.nila header { position:sticky; top:0; z-index:40; background:color-mix(in srgb, var(--ground) 88%, transparent); backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }
.nav { display:flex; align-items:center; gap:18px; height:68px; }
.brand { display:flex; align-items:center; gap:11px; }
.logo-ph { width:42px; height:42px; flex:none; border-radius:11px; border:1.5px dashed var(--faint); background:var(--surface-2); display:grid; place-items:center; gap:1px; color:var(--faint); font-size:0.52rem; font-weight:700; letter-spacing:0.08em; }
.logo-ph svg { width:17px; height:17px; }
.logo-img { width:42px; height:42px; flex:none; border-radius:11px; object-fit:cover; }
.brand-name { font-family:var(--font-display); font-size:1.16rem; font-weight:600; line-height:1.05; white-space:nowrap; }
.brand-name b { color:var(--gold); font-weight:600; display:block; font-size:0.82rem; }
.nila.lang-ta .brand-name b { font-size:0.72rem; }
.nav-links { display:flex; gap:20px; margin-left:auto; }
.nav-links a { font-size:0.9rem; font-weight:500; color:var(--muted); }
.nav-links a:hover { color:var(--ink); }
.nav-right { display:flex; align-items:center; gap:10px; }
@media (max-width:940px) { .nav-links { display:none; } .nav-right { margin-left:auto; } }
@media (max-width:480px) {
  .nav { gap:8px; height:62px; } .brand { gap:8px; }
  .logo-ph, .logo-img { width:36px; height:36px; } .logo-ph { font-size:0.46rem; } .logo-ph svg { width:15px; height:15px; }
  .brand-name { font-size:0.98rem; } .brand-name b { font-size:0.6rem; }
  .nav-right { gap:7px; } .lang button { padding:4px 7px; font-size:0.72rem; } .btn { padding:8px 12px; font-size:0.82rem; }
}
@media (max-width:360px) { .brand-name b { display:none; } }
.lang { display:inline-flex; border:1px solid var(--line); border-radius:999px; padding:3px; background:var(--surface); }
.lang button { border:none; background:none; cursor:pointer; color:var(--muted); font:inherit; font-size:0.8rem; font-weight:600; padding:4px 10px; border-radius:999px; }
.lang button.on { background:var(--night); color:var(--on-night); }
.btn { display:inline-flex; align-items:center; gap:8px; cursor:pointer; font:inherit; font-weight:600; font-size:0.9rem; padding:9px 17px; border-radius:999px; border:1px solid transparent; transition:transform 0.12s ease, background 0.15s ease; }
.btn:active { transform:translateY(1px); }
.btn:disabled { opacity:0.7; cursor:default; }
.btn-gold { background:var(--gold); color:#241a08; }
.btn-gold:hover { background:color-mix(in srgb, var(--gold) 88%, #000); }
.btn-ghost-night { border-color:color-mix(in srgb, var(--on-night) 32%, transparent); color:var(--on-night); background:transparent; }
.btn-ghost-night:hover { background:color-mix(in srgb, var(--on-night) 12%, transparent); }
.hero { position:relative; overflow:hidden; background:linear-gradient(160deg, var(--night) 0%, var(--night-2) 100%); color:var(--on-night); border-bottom:1px solid var(--line-night); }
.hero .wrap { padding-block:clamp(52px, 8vw, 96px); position:relative; z-index:2; }
.hero-inner { max-width:650px; }
.hero h1 { font-size:clamp(2.3rem, 5.5vw, 3.9rem); line-height:1.05; letter-spacing:-0.015em; margin:18px 0 20px; }
.nila.lang-ta .hero h1 { font-size:clamp(1.85rem, 5vw, 3rem); line-height:1.3; }
.hero p.lede { font-size:1.12rem; color:var(--on-night-muted); max-width:35rem; }
.hero-cta { display:flex; flex-wrap:wrap; gap:12px; margin-top:28px; }
.crescent { position:absolute; z-index:1; top:-60px; right:-60px; width:420px; height:420px; border-radius:50%; background:radial-gradient(circle at 64% 36%, rgba(224,172,95,0.20) 0 44%, transparent 45%); }
.crescent::after { content:""; position:absolute; inset:26% 26%; border-radius:50%; box-shadow:inset -18px -14px 0 -2px rgba(224,172,95,0.5); }
@media (max-width:620px) { .crescent { width:250px; height:250px; top:-40px; right:-70px; } }
.stats { background:var(--surface); border-bottom:1px solid var(--line); }
.stats .wrap { display:grid; grid-template-columns:repeat(3, 1fr); gap:0; padding:0; }
.stat { padding:24px 22px; }
.stat + .stat { box-shadow:-1px 0 0 var(--line); }
.stat .num { font-family:var(--font-display); font-size:1.9rem; font-weight:600; color:var(--gold); font-variant-numeric:tabular-nums; }
.stat .lbl { font-size:0.8rem; color:var(--muted); margin-top:2px; }
@media (max-width:760px) { .stats .wrap { grid-template-columns:1fr 1fr; } .stat:nth-child(odd) { box-shadow:none; } .stat { border-top:1px solid var(--line); } .stat:nth-child(-n+2) { border-top:none; } }
.block { padding-block:clamp(52px, 7vw, 88px); }
.section-head { max-width:650px; margin-bottom:34px; }
.section-head.center { margin-inline:auto; text-align:center; }
.section-head h2 { font-size:clamp(1.9rem, 4vw, 2.6rem); line-height:1.12; margin:10px 0 12px; }
.section-head p { color:var(--muted); font-size:1.04rem; }
.carousel { position:relative; }
.track { display:flex; gap:16px; overflow-x:auto; scroll-snap-type:x mandatory; scroll-behavior:smooth; -ms-overflow-style:none; scrollbar-width:none; padding:2px 2px 8px; }
.track::-webkit-scrollbar { display:none; }
.slide { scroll-snap-align:start; flex:0 0 auto; }
.car-nav { display:flex; gap:8px; }
.car-btn { width:40px; height:40px; border-radius:50%; border:1px solid var(--line); background:var(--surface); color:var(--ink); cursor:pointer; display:grid; place-items:center; }
.car-btn:hover { border-color:var(--gold); color:var(--gold); }
.car-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:22px; }
.focus { flex:0 0 300px; max-width:82vw; background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:22px; }
.focus .ic { width:42px; height:42px; border-radius:11px; display:grid; place-items:center; background:var(--gold-soft); color:var(--gold); margin-bottom:14px; }
.focus .ic svg { width:21px; height:21px; }
.focus h3 { font-size:1.15rem; margin-bottom:6px; }
.focus p { color:var(--muted); font-size:0.94rem; }
.services { display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; }
@media (max-width:900px) { .services { grid-template-columns:1fr 1fr; } }
@media (max-width:560px) { .services { grid-template-columns:1fr; } }
.service { background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:22px; transition:transform 0.15s ease, box-shadow 0.15s ease; }
.service:hover { transform:translateY(-3px); box-shadow:0 14px 30px -18px rgba(30,35,64,0.35); }
.service .ic { width:42px; height:42px; border-radius:11px; display:grid; place-items:center; background:var(--gold-soft); color:var(--gold); margin-bottom:14px; }
.service .ic svg { width:21px; height:21px; }
.service h3 { font-size:1.15rem; margin-bottom:6px; }
.service p { color:var(--muted); font-size:0.94rem; }
.gallery { background:var(--night); color:var(--on-night); }
.gslide { flex:0 0 100%; scroll-snap-align:center; border-radius:18px; overflow:hidden; position:relative; aspect-ratio:16 / 7; min-height:240px; background-size:cover; background-position:center; }
.gslide .ph { position:absolute; inset:0; display:grid; place-items:center; color:rgba(255,255,255,0.85); }
.gslide .ph svg { width:46px; height:46px; opacity:0.9; }
.gslide .cap { position:absolute; left:20px; bottom:18px; right:20px; z-index:2; }
.gslide .cap .t { font-family:var(--font-display); font-size:1.4rem; }
.gslide .cap .s { font-size:0.78rem; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.7); }
.gslide::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg, transparent 40%, rgba(0,0,0,0.45)); z-index:1; }
.g1 { background:linear-gradient(135deg,#2b3a67,#4a5a8a); } .g2 { background:linear-gradient(135deg,#3a5a52,#6e8b82); }
.g3 { background:linear-gradient(135deg,#5a4a7a,#8a6ea9); } .g4 { background:linear-gradient(135deg,#7a5a3a,#c8893a); }
.g5 { background:linear-gradient(135deg,#3a4a5a,#5a7a8a); } .g6 { background:linear-gradient(135deg,#4a3a5a,#7a5a8a); }
.dots { display:flex; gap:8px; justify-content:center; margin-top:18px; }
.dots button { width:8px; height:8px; border-radius:50%; border:none; background:rgba(255,255,255,0.3); cursor:pointer; padding:0; }
.dots button.on { background:var(--gold); width:22px; border-radius:999px; }
.timetable { background:var(--surface-2); border-block:1px solid var(--line); }
.tt-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px 26px; }
@media (max-width:700px) { .tt-grid { grid-template-columns:1fr; } }
.tt-row { display:flex; align-items:center; gap:14px; padding:11px 14px; background:var(--surface); border:1px solid var(--line); border-radius:12px; }
.tt-row .time { font-family:var(--font-body); font-weight:700; font-variant-numeric:tabular-nums; color:var(--gold); font-size:0.92rem; min-width:52px; }
.tt-row .act { font-size:0.97rem; }
.tt-note { font-size:0.82rem; color:var(--faint); margin-top:18px; text-align:center; }
.about-grid { display:grid; grid-template-columns:1.1fr 0.9fr; gap:48px; align-items:center; }
@media (max-width:820px) { .about-grid { grid-template-columns:1fr; gap:28px; } }
.about-grid h2 { font-size:clamp(1.9rem, 4vw, 2.5rem); line-height:1.12; margin-bottom:16px; }
.about-grid p { color:var(--muted); }
.about-card { background:var(--night); color:var(--on-night); border-radius:20px; padding:30px; }
.about-card .q { font-family:var(--font-display); font-size:1.4rem; line-height:1.4; }
.about-card .by { margin-top:16px; color:var(--on-night-muted); font-size:0.88rem; }
.contact-grid { display:grid; grid-template-columns:1fr 1fr; gap:40px; }
@media (max-width:760px) { .contact-grid { grid-template-columns:1fr; gap:24px; } }
.contact-row { display:flex; gap:14px; align-items:flex-start; padding:15px 0; border-top:1px solid var(--line); }
.contact-row:first-of-type { border-top:none; }
.contact-row .ic { color:var(--gold); margin-top:2px; }
.contact-row .k { font-size:0.76rem; text-transform:uppercase; letter-spacing:0.12em; color:var(--faint); }
.nila.lang-ta .contact-row .k { letter-spacing:0.03em; text-transform:none; }
.contact-row .v { font-size:1.1rem; font-weight:600; }
.contact-row .v a:hover { color:var(--gold); }
.socials { display:flex; gap:10px; margin-top:8px; }
.socials a { width:38px; height:38px; border-radius:50%; border:1px solid var(--line); display:grid; place-items:center; color:var(--muted); }
.socials a:hover { border-color:var(--gold); color:var(--gold); }
.enquire { background:var(--surface); border:1px solid var(--line); border-radius:18px; padding:26px; }
.field { margin-bottom:14px; }
.field label { display:block; font-size:0.82rem; font-weight:600; color:var(--muted); margin-bottom:6px; }
.field input, .field textarea { width:100%; font:inherit; font-size:0.95rem; padding:11px 13px; border:1px solid var(--line); border-radius:10px; background:var(--ground); color:var(--ink); }
.field input:focus, .field textarea:focus { outline:2px solid var(--gold); outline-offset:1px; border-color:transparent; }
.nila footer { background:var(--night); color:var(--on-night-muted); }
.nila footer .wrap { padding-block:30px; display:flex; flex-wrap:wrap; gap:16px; align-items:center; justify-content:space-between; }
.nila footer .fbrand { color:var(--on-night); font-family:var(--font-display); font-size:1.1rem; font-weight:600; }
.nila footer small { font-size:0.82rem; }
.overlay { position:fixed; inset:0; z-index:100; display:none; background:rgba(16,19,42,0.55); backdrop-filter:blur(3px); align-items:center; justify-content:center; padding:18px; }
.overlay.open { display:flex; }
.modal { width:100%; max-width:400px; background:var(--surface); border:1px solid var(--line); border-radius:20px; padding:26px; box-shadow:0 30px 70px -30px rgba(16,19,42,0.6); }
.modal-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.modal h3 { font-size:1.4rem; }
.modal .sub { color:var(--muted); font-size:0.9rem; margin-bottom:18px; }
.x { border:none; background:none; cursor:pointer; color:var(--faint); font-size:1.3rem; line-height:1; padding:2px 6px; }
.msg { font-size:0.86rem; margin-top:10px; min-height:1.2em; }
.msg.err { color:#c0392b; } .msg.ok { color:var(--sage); font-weight:600; }
.recaptcha-note { font-size:0.72rem; color:var(--faint); margin-top:14px; text-align:center; }
.nila :focus-visible { outline:2px solid var(--gold); outline-offset:2px; }
@media (prefers-reduced-motion: reduce) { .nila *, .nila { transition:none !important; animation:none !important; scroll-behavior:auto !important; } }
`;
