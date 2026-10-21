import {post} from "@/api/core";

export type Login = {
    "login": string,
    "password": string
}

export function login(data: Login) {
    return post("/auth/login", data, false)
}