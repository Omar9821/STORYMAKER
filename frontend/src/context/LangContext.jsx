import { createContext, useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

const LangContext = createContext(null);

export const useLang = () => useContext(LangContext);

export const LangProvider = ({ children }) => {
  const { i18n } = useTranslation();
  const [lang, setLang] = useState(localStorage.getItem("hikayati_lang") || "ar");

  const dir = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.setAttribute("dir", dir);
    document.documentElement.setAttribute("lang", lang);
    i18n.changeLanguage(lang);
    localStorage.setItem("hikayati_lang", lang);
  }, [lang, dir, i18n]);

  return (
    <LangContext.Provider value={{ lang, setLang, dir }}>
      {children}
    </LangContext.Provider>
  );
};
