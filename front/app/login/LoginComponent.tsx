"use client"

import "@/app/globals.css"
import {ChangeEventHandler, SubmitEventHandler, useState} from "react";
import {login} from "@/api/login";
import {waited} from "@/api/core";
import {useRouter, useSearchParams} from "next/navigation";

export default function () {
    const [data, setData] = useState({
        "login": "",
        "password": ""
    });
    const [state, setState] = useState<string | null | undefined>(null)
    const params = useSearchParams()
    const router = useRouter();

    const onChange: ChangeEventHandler<HTMLInputElement, HTMLInputElement> = function (e) {
        setData(prev => ({...prev, [e.target.name]: e.target.value}))
    }

    const send: SubmitEventHandler<HTMLFormElement> = function (e) {
        e.preventDefault()

        waited([login(data), null], res => {
            if (res !== null && res !== undefined) {
                if (res.ok) {
                    setState(null)
                    router.replace(params.get("from") || "/home") // TODO FIXME vulnerability open redirect
                    router.refresh()
                } else {
                    setState(res.error_str())
                }
            } else if (res !== undefined) {
                setState("No response from proxy");
            }
        }, e => setState(String(e)))
    }

    return (
        <form method="POST" onSubmit={send} className="size-full flex flex-col items-center justify-center gap-4 p-4 flex-1 w-3/5 h-full">
            <div className="grid grid-cols-[auto_1fr] gap-4 w-full">
                <label className="text-lg font-semibold text-right">Login</label>
                <input
                    name="login"
                    value={data.login}
                    onChange={onChange}
                    className="w-full input"
                />
                <label className="text-lg font-semibold text-right">Password</label>
                <input
                    name="password"
                    value={data.password}
                    onChange={onChange}
                    type="password"
                    className="w-full input"
                />
            </div>

            <button type="submit" disabled={state === undefined} className="w-full btn-primary">
                {state === undefined ? "pls wait" : "login"}
            </button>
            <span className="text-red-600"> { typeof(state) == "string" && state } </span>
        </form>
    )
}