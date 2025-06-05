# pruebagemini_clean.py

from google import genai

# 1) Crea el cliente GenAI con tu API Key (reemplaza YOUR_API_KEY por la real)
client = genai.Client(api_key="AIzaSyBHCR2HrTrQLnyhaRFxii6fkJ1L_U9pQe4")

def preguntar_gemini_genai(prompt_text):
    """
    Envía 'prompt_text' al modelo Gemini (por ejemplo, gemini-1.5-flash)
    usando genai.Client y devuelve la respuesta limpia sin "***".
    """
    # Llamada mínima a Gemini (sin temperatura ni max_output_tokens)
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt_text
    )

    # Obtenemos el texto bruto
    texto = response.text

    # 1) Eliminamos todos los triples asteriscos "***"
    texto = texto.replace("***", "")

    # 2) También podemos limpiar dobles asteriscos "**" si hubiese
    texto = texto.replace("**", "")

    # 3) Finalmente, borramos espacios en blanco al principio/fin
    texto = texto.strip()

    return texto

if __name__ == "__main__":
    prompt = "¿Quién fue Albert Einstein y cuál fue su contribución a la física?"
    print("Prompt:", prompt)

    respuesta = preguntar_gemini_genai(prompt)
    print("\nRespuesta de Gemini (GenAI) limpia:\n")
    print(respuesta)
