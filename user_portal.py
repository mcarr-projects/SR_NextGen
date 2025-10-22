import tkinter as tk
from tkinter import messagebox

root = tk.Tk()
root.title("Spaced Repition Practice")

add_card_btn = tk.Button(root, text="Add Question")
add_card_btn.pack(pady=10)

review_card_btn = tk.Button(root, text="Review Questions")
review_card_btn.pack(pady=10)

root.mainloop()