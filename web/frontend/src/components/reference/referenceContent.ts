/**
 * What the language actually accepts, as data.
 *
 * Kept separate from the component that renders it so that extending the
 * grammar means editing this one list, next to nothing else.
 */

export interface ReferenceEntry {
  code: string;
  note: string;
}

export interface ReferenceSection {
  title: string;
  description?: string;
  entries: ReferenceEntry[];
}

export const SYNTAX_REFERENCE: ReferenceSection[] = [
  {
    title: "Програма",
    entries: [
      { code: "begin ... end", note: "P1. Програма - рівно один блок begin ... end; після нього нічого не може бути." },
    ],
  },
  {
    title: "Оператори",
    description: "';' зв'язує найслабше: тіло while і гілка else - один оператор, для кількох потрібен begin ... end.",
    entries: [
      { code: "X := a", note: "S1. Присвоювання." },
      { code: "S1; S2", note: "S2. Послідовне виконання. Після останнього оператора ';' не ставиться." },
      { code: "if b then S1 else S2", note: "S3. Гілка else обов'язкова. Гілка then може містити ';'." },
      { code: "while b do S", note: "S4. Умова перевіряється перед кожною ітерацією." },
      { code: "begin S end", note: "S5. Вкладений блок." },
      { code: "skip", note: "S6. Порожній оператор." },
    ],
  },
  {
    title: "Арифметичні вирази",
    description: "Від найнижчого пріоритету до найвищого. Бінарні оператори лівоасоціативні.",
    entries: [
      { code: "a1 + a2   a1 - a2", note: "A3, A4. Додавання й віднімання: 8 - 4 - 2 = (8 - 4) - 2." },
      { code: "a1 * a2", note: "A5. Множення. Ділення в SIPL немає." },
      { code: "(a)", note: "A6. Дужки." },
      { code: "X   Count   x_1", note: "A2. Змінна: латинська літера, далі літери, цифри, '_'. Ключові слова зарезервовані." },
      { code: "0   42   -1", note: "A1. Ціле число без обмеження розміру. Мінус без пробілу належить числу: X - -1." },
      { code: "-X   - 1", note: "Помилка: унарного мінуса немає. Замість -X пишіть 0 - X." },
    ],
  },
  {
    title: "Умови",
    description: "Від найнижчого пріоритету до найвищого.",
    entries: [
      { code: "b1 ∨ b2   b1 or b2", note: "B3. Диз'юнкція. Обчислюються обидві частини." },
      { code: "¬b   not b", note: "B4. Заперечення." },
      { code: "a1 = a2   a1 > a2", note: "B1, B2. Порівняння. Інших (<, ≤, ≠) немає: замість X < Y пишіть Y > X." },
      { code: "(b)", note: "B5. Дужки." },
    ],
  },
  {
    title: "Виконання",
    entries: [
      { code: "X = 2, Y = 10", note: "Початковий стан задається на панелі виконання." },
      { code: "Y := Z + 1", note: "Читання змінної без значення - помилка виконання." },
      { code: "while 1 = 1 do skip", note: "Нескінченний цикл зупиняється на ліміті кроків." },
    ],
  },
];