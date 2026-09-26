"use client";

import { createContext, useContext } from "react";

export const ScanDialogContext = createContext<{ open: () => void }>({ open: () => {} });
export const useScanDialog = () => useContext(ScanDialogContext);
