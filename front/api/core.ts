import {RestResponse} from "@/api/types";
import {Dispatch, SetStateAction} from "react";

function normalizeEndpoint(endpoint: string) {
    return endpoint.replace(/^\/+/, "")
}

export async function request(endpoint: string, method: string, body: object | null | undefined, redirectOnUnauthorized = true) {
    try {
        const isServer = (typeof window) === "undefined"
        //console.log(endpoint, isServer)
        const normalizedEndpoint = normalizeEndpoint(endpoint)

        const response = await (
            isServer
                ? backRequest(normalizedEndpoint, method, new Headers(), body ? JSON.stringify(body) : null)
                : fetch(`/api/proxy/${normalizedEndpoint}`, {
                    method: method,
                    headers: {"Content-Type": "application/json"},
                    body: body ? JSON.stringify(body) : null,
                    cache: "no-cache"
                })
        )

        if (response.status == 401 && redirectOnUnauthorized) {
            if (isServer) {
                const {redirect} = await import("next/navigation");

                redirect("/login")
            } else window.location.href = "/login";
        }

        const text = await response.text()
        let responseBody: any = null
        if (text) {
            try {
                responseBody = JSON.parse(text)
            } catch (e) {
                responseBody = text
            }
        }
        return new RestResponse(response.ok ? responseBody : {body: responseBody, code: response.status}, response.ok)
    } catch (error: any) {
        if (error?.code === 'ECONNREFUSED' ||
            error?.cause?.code === 'ECONNREFUSED' ||
            error?.message?.includes('fetch failed'))
            return new RestResponse({ body: {}, code: 503 }, false)

        throw error
    }
}

export function post(endpoint: string, body: object, redirectOnUnauthorized: boolean = true) {
    return request(endpoint, "POST", body, redirectOnUnauthorized)
}

export function get(endpoint: string, redirectOnUnauthorized: boolean = true) {
    return request(endpoint, "GET", null, redirectOnUnauthorized)
}

/** undefined - loading, value - ok */
export function waited<T>(promise: Promise<T>, set: Dispatch<SetStateAction<T | null | undefined>>) {
    set(undefined)
    promise.then(value => {
        set(value)
    }, error => {
        throw new Error("Failed to access to API service due to:\n" + JSON.stringify(error))
    })
}

export async function backRequest(endpoint: string, method: string, requestHeaders: Headers, body: BodyInit | null | undefined) {
    if (process.env.BACK_HOST === undefined)
        throw new Error("env variable BACK_HOST is not set")
    const BACKEND_URL = `${process.env.NODE_ENV === "production" ? "https" : "http"}://${process.env.BACK_HOST}`

    const {cookies, headers} = await import("next/headers")

    const originalHeaders = await headers();
    const cookieStore = await cookies();

    const targetUrl = `${BACKEND_URL}/${endpoint
        .replace(/\\/g, '/')
        .replace(/\/+/g, '/')
        .replace(/^\/|\/\$/g, '')
    }`

    // add to headers forwarding parameters
    const forwardedFor = originalHeaders.get("x-forwarded-for");
    const clientIp = forwardedFor
        ? forwardedFor.split(",")[0].trim()
        : (originalHeaders.get("x-real-ip") || "127.0.0.1");
    requestHeaders.set("X-Forwarded-For", clientIp);

    const token = cookieStore.get("auth_token")?.value
    if (token) requestHeaders.set("Authorization", `Bearer ${token}`)

    return fetch(targetUrl, {
        method: method,
        headers: requestHeaders,
        body: body,
        cache: "no-store",
        // @ts-ignore Node.js requires this option
        duplex: "half"
    })
}