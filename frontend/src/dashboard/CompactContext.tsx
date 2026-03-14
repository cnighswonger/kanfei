import { createContext, useContext } from "react";

const CompactContext = createContext(false);

export const CompactProvider = CompactContext.Provider;

export function useCompact(): boolean {
  return useContext(CompactContext);
}
