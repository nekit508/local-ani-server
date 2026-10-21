import "./globals.css"
import React from "react";
import GlobalNavigator from "@/components/GlobalNavigator";

export default function Layout({ children, }: { children: React.ReactNode }) {
    return (
        <html lang="en" className="size-full">
        <body className="size-full">
        <div className="size-full flex-col">
            <GlobalNavigator/>
            { children }
        </div>
        </body>
        </html>
    )
}