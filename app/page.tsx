import BooksList from "@/components/BookList"
import {Metadata} from "next";

export const metadata: Metadata = {
    title: "Libros de Gutendex",
    description: "Explora libro de Gutendex",
}

export default function Page() {
    return <BooksList />
}