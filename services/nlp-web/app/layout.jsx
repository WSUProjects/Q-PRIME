import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { withBasePath } from "@/lib/basePath";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

const geistMono = Geist_Mono({
    variable: "--font-geist-mono",
    subsets: ["latin"],
});

export const metadata = {
    title: "Q-PRIME IoT Assistant",
    description:
        "Ask questions about IoT data exposed by your configured query source.",
    icons: {
        icon: [{ url: withBasePath("/icon.png"), type: "image/png" }],
    },
};

export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body
                className={`${geistSans.variable} ${geistMono.variable} antialiased`}
            >
                {children}
            </body>
        </html>
    );
}
