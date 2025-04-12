"""
print("Hello world!")
for volte in range(1,11):
    print(f"{volte:>2}")
"""

def funzione_contenitore(fun_passata):
    print("Funzione contenitore.")
    fun_passata()
    print("Fine funzione contenitore.")

def fun_a():
    print("Funzione A.")

def fun_b():
    print("Funzione B.")
    
funzione_contenitore(fun_b)


