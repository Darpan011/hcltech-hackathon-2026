import { useEffect, useState } from "react";
import api from "./api.js";

/** Reads whether online self-service is on (SELF_SERVICE_ONBOARDING) or customers are onboarded at the branch. */
export function useOnboardingConfig() {
  const [config, setConfig] = useState(null);
  useEffect(() => {
    api.get("/auth/config").then((r) => setConfig(r.data)).catch(() => setConfig({ self_service_onboarding: false }));
  }, []);
  return config;
}
