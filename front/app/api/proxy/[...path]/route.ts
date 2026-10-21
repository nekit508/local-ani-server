// noinspection ES6UnusedImports

import {NextRequest, NextResponse} from "next/server"
import {cookies} from "next/headers"
import {backRequest} from "@/api/core";

interface RouteParams {
    params: Promise<{ path: string[] }>
}

interface BackendTokenResponse {
    token: string;
}

enum TokenActionType {
    DELETE = "DELETE",
    SAVE = "SAVE"
}

interface TokenAction {
    type: TokenActionType
    token: string
}

if (!Number.isFinite(Number(process.env.JWT_COOKIE_LIFETIME)))
    throw new Error("env JWT_COOKIE_LIFETIME is not set")

const headersToSkip = new Set(["host", "cookie", "authorization"])
const methodsToBypassBody = new Set(["POST", "PUT", "PATCH", "DELETE"])

async function handleProxy(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
    try {
        const pathSegments = (await params).path;
        const targetPath = pathSegments.join("/");

        const { search } = new URL(request.url);
        const targetUrl = `${targetPath}${search}`;

        let body: ReadableStream<Uint8Array> | null = null;
        if (methodsToBypassBody.has(request.method))
            body = request.body

        const requestHeaders = new Headers()
        request.headers.forEach((value, key) => {
            if (!headersToSkip.has(key.toLowerCase()))
                requestHeaders.set(key, value)
        });

        const backendResponse = await backRequest(targetUrl, request.method, requestHeaders, body)

        // try to determine token invalidation
        // we are unauthorized but token was provided, so it's probably invalidated, and we need new
        console.log(JSON.stringify(backendResponse))
        if (backendResponse.status === 401 && (await cookies()).has("auth_token")) {
            console.log("inv redir")
            const response = NextResponse.json(
                { error: "Token is expired or invalidated or you are unauthorized" },
                { status: backendResponse.status }
            )
            response.cookies.set("auth_token", "", { expires: new Date(0), path: "/" })
            return response
        }

        const response = new NextResponse(await backendResponse.text(), {
            status: backendResponse.status,
            headers: {
                "Content-Type": backendResponse.headers.get("Content-Type") || "application/json",
            }
        })

        const tokenAction = backendResponse.headers.get("X-JWT-Action");
        //console.log(tokenAction)
        if (tokenAction !== null) {
            const action = JSON.parse(tokenAction) as TokenAction
            if (action.type == TokenActionType.SAVE) {
                response.cookies.set("auth_token", action.token, {
                    httpOnly: true,
                    secure: process.env.NODE_ENV === "production",
                    sameSite: "strict",
                    maxAge: Number(process.env.JWT_COOKIE_LIFETIME),
                    path: "/",
                });
            } else if (action.type == TokenActionType.DELETE) {
                response.cookies.set("auth_token", "", { expires: new Date(0), path: "/" })
            }
        }

        return response
    } catch (error: any) {
        const isConnectionRefused =
            error?.code === 'ECONNREFUSED' ||
            error?.cause?.code === 'ECONNREFUSED' ||
            error?.message?.includes('fetch failed');

        if (isConnectionRefused) {
            return NextResponse.json(
                { error: "Back not responds" },
                { status: 503 }
            );
        }

        console.error("BFF Proxy Error:", error)
        return NextResponse.json({ error: "Internal Proxy Server Error" }, { status: 500 })
    }
}

export const GET = handleProxy;
export const POST = handleProxy;
export const PUT = handleProxy;
export const DELETE = handleProxy;