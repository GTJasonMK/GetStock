import type { Metadata } from "next";
import { Agentation } from "agentation";
import ToastProvider from "@/components/ui/ToastProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Recon - Python Backend",
  description: "Stock analysis application with Python FastAPI backend",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh" className="h-full">
      <body className="h-full antialiased">
        <ToastProvider>
          {children}
          {process.env.NODE_ENV === "development" && <Agentation />}
        </ToastProvider>
      </body>
    </html>
  );
}
