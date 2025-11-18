"use client"

import { useEffect, useState } from "react"
import { BookOpen, AlertCircle, Loader } from "lucide-react"

type Author = { name: string }
type Book = { id: number; title: string; authors: Author[] }
type GutendexResponse = { results: Book[] }

export default function BooksList() {
    const [items, setItems] = useState<Book[]>([])
    const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const controller = new AbortController()
        ;(async () => {
            try {
                const res = await fetch("https://gutendex.com/books/?page=1", {
                    signal: controller.signal,
                })
                if (!res.ok) {
                    setError(`HTTP ${res.status}`);
                    setStatus("error");
                    return;
                }
                const json: GutendexResponse = await res.json()
                setItems((json.results ?? []).slice(0, 10))
                setStatus("success")
            } catch (e: unknown) {
                if (!(e instanceof DOMException && e.name === "AbortError")) {
                    setError(e instanceof Error ? e.message : "Error inesperado");
                    setStatus("error");
                }
            }
        })()

        return () => controller.abort()
    }, [])

    if (status === "loading") {
        return (
            <div className="min-h-screen bg-linear-to-br from-background via-background to-slate-50 dark:to-slate-950 flex items-center justify-center p-4">
                <div className="text-center">
                    <Loader className="w-8 h-8 text-primary animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground text-lg">Cargando libros...</p>
                </div>
            </div>
        )
    }

    if (status === "error") {
        return (
            <div className="min-h-screen bg-linear-to-br from-background via-background to-slate-50 dark:to-slate-950 flex items-center justify-center p-4">
                <div className="text-center max-w-md">
                    <AlertCircle className="w-12 h-12 text-destructive mx-auto mb-4" />
                    <p className="text-destructive font-semibold mb-2">Error al cargar los libros</p>
                    <p className="text-muted-foreground">{error}</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-linear-to-br from-background via-background to-slate-50 dark:to-slate-950">
            {/* Header Section */}
            <div className="relative py-16 px-4 sm:px-6 lg:px-8">
                <div className="max-w-6xl mx-auto">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-3 rounded-xl bg-primary/10">
                            <BookOpen className="w-6 h-6 text-primary" />
                        </div>
                        <span className="text-sm font-semibold text-primary">BIBLIOTECA DIGITAL</span>
                    </div>
                    <h1 className="text-4xl sm:text-5xl font-bold text-foreground mb-3 text-balance">
                        Libros de Gutendex
                    </h1>
                </div>
            </div>

            {/* Books Grid */}
            <div className="px-4 sm:px-6 lg:px-8 pb-16">
                <div className="max-w-6xl mx-auto">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {items.map((book) => (
                            <div
                                key={book.id}
                                className="group relative overflow-hidden rounded-2xl bg-card border border-border/50 hover:border-primary/30 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5"
                            >
                                {/* Decorative background */}
                                <div className="absolute inset-0 bg-linear-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                                {/* Content */}
                                <div className="relative p-6 flex flex-col h-full">
                                    {/* Icon */}
                                    <div className="mb-4 inline-flex w-fit p-3 rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
                                        <BookOpen className="w-5 h-5 text-primary" />
                                    </div>

                                    {/* Title */}
                                    <h2 className="font-bold text-lg text-foreground mb-2 line-clamp-2 group-hover:text-primary transition-colors leading-tight">
                                        {book.title}
                                    </h2>

                                    {/* Author */}
                                    <p className="text-sm text-muted-foreground line-clamp-1 grow">
                                        {book.authors?.[0]?.name ?? "Autor desconocido"}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Footer Stats */}
            <div className="border-t border-border/30 py-8 px-4 sm:px-6 lg:px-8">
                <div className="max-w-6xl mx-auto text-center">
                    <p className="text-sm text-muted-foreground">
                        Mostrando <span className="font-semibold text-foreground">{items.length}</span> libros de una colección
                        extensa
                    </p>
                </div>
            </div>
        </div>
    )
}