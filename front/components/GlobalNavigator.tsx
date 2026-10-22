"use client"

import Link from "next/link";
import {usePathname} from "next/navigation";
import React from "react";

export default function () {
    const path = usePathname()
    return (
        <div className="flex flex-row items-start justify-center gap-4 p-4 border-b-1 border-foreground/50">
            <VarLink current={path} target={"/search"}> Search </VarLink>
            <VarLink current={path} target={"/workers"}> Downloads </VarLink>
            <VarLink current={path} target={"/files"}> Files </VarLink>
            <VarLink current={path} target={"/home"}> Home </VarLink>
        </div>
    )
}

function VarLink({ target, current, children } : { target: string, current: string, children: React.ReactNode }) {
    return current != target && <Link href={target} className="btn-primary p-2 flex flex-row items-center"> { children } </Link>
}