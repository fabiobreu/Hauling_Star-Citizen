# Star Citizen Hauling Monitor

Ferramenta de monitoramento de missões de transporte (Hauling) para Star Citizen. Esta aplicação lê o arquivo de log do jogo em tempo real (`Game.log`) para rastrear missões aceitas, atualizações de carga, entregas e recompensas, exibindo tudo em um Dashboard Web interativo.

## 🚀 Funcionalidades

-   **Rastreamento Automático**: Detecta missões de Hauling aceitas, coleta de carga e entregas diretamente do log do jogo.
-   **Dashboard Web**: Interface visual moderna e responsiva (Dark Mode) para acompanhar suas missões em um segundo monitor, tablet ou celular.
-   **Multi-Idioma**: Suporte completo para Português (PT) e Inglês (EN), configurável via arquivo JSON.
-   **Edição Manual**: Permite adicionar itens manualmente caso o log não capture algum evento ou para missões antigas.
-   **Histórico de Missões**: Salva missões concluídas, canceladas ou falhas, com cálculo de ganhos totais e tempo de missão.
-   **Persistência**: O estado atual é salvo automaticamente (`hauling_state.json`), permitindo fechar e reabrir a ferramenta sem perder o progresso.
-   **Identificação**: Detecta automaticamente o nome do jogador e a nave utilizada.

## 🛠️ Instalação e Execução

### Pré-requisitos
-   Python 3.8 ou superior instalado.
-   Bibliotecas Python necessárias (instale via pip):
    ```bash
    pip install flask
    ```

### Como Rodar
1.  Clone este repositório.
2.  Verifique o caminho do seu arquivo de log no `hauling_config.json` (veja a seção de Configuração abaixo).
3.  Execute o script principal:
    ```bash
    python hauling_web_tst.py
    ```
4.  Abra o navegador no endereço indicado (geralmente `http://0.0.0.0:5000` ou `http://localhost:5000`).

## ⚙️ Configuração (`hauling_config.json`)

O arquivo `hauling_config.json` controla o comportamento da ferramenta. As principais opções são:

*   `"log_path"`: Caminho absoluto para o arquivo `Game.log` do Star Citizen.
    *   Exemplo: `"C:/Program Files/Roberts Space Industries/StarCitizen/LIVE/Game.log"`
*   `"language"`: Define o idioma da interface (`"pt"` para Português, `"en"` para Inglês).
*   `"web_port"`: Porta para o servidor web (padrão: `5000`).
*   `"refresh_interval_ms"`: Intervalo de atualização da página em milissegundos (padrão: `2000`).

## 🌍 Tradução e Internacionalização

O sistema de tradução é baseado em arquivos JSON. Para alterar o idioma ou adicionar um novo:

1.  Edite o parâmetro `"language"` em `hauling_config.json`.
2.  Certifique-se de que existe um arquivo correspondente `hauling_lang_{LANGUAGE}.json` (ex: `hauling_lang_pt.json`).
3.  **Para contribuir com um novo idioma**:
    *   Copie o arquivo `hauling_lang_en.json`.
    *   Renomeie para `hauling_lang_fr.json` (por exemplo, para Francês).
    *   Traduza os valores das chaves (não altere as chaves!).
    *   Envie um Pull Request!

## 🤝 Como Contribuir

Contribuições são bem-vindas! Se você quiser melhorar o código, adicionar funcionalidades ou corrigir bugs:

1.  Faça um **Fork** do projeto.
2.  Crie uma **Branch** para sua feature (`git checkout -b feature/nova-feature`).
3.  Faça o **Commit** das suas alterações (`git commit -m 'Adiciona nova feature'`).
4.  Faça o **Push** para a Branch (`git push origin feature/nova-feature`).
5.  Abra um **Pull Request**.

### Áreas para Melhoria
*   Refinamento das Regex para capturar mais variações de logs de missões.
*   Melhorias na interface UI/UX do Dashboard.
*   Suporte a mais tipos de missões (além de Hauling).

## 📂 Estrutura de Arquivos

*   `hauling_web_tst.py`: Código principal da aplicação (Servidor Flask + Parser de Log).
*   `hauling_config.json`: Arquivo de configuração.
*   `hauling_lang_pt.json`: Arquivo de tradução PT-BR.
*   `hauling_lang_en.json`: Arquivo de tradução EN.
*   `hauling_state.json`: Arquivo gerado automaticamente para salvar o progresso (não deve ser commitado).

---
Desenvolvido pela comunidade para a comunidade. Fly safe! o7
