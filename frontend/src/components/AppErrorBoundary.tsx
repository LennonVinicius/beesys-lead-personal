import React from 'react'

type State = { hasError: boolean }

export class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    console.error('[BeeSys Lead Search] Erro não tratado no frontend', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <main className="grid min-h-screen place-items-center bg-background p-6">
        <section className="w-full max-w-lg rounded-2xl border border-border bg-surface p-8 shadow-sm">
          <p className="text-sm font-semibold text-primary">BeeSys Lead Search</p>
          <h1 className="mt-2 text-2xl font-bold text-ink">Não foi possível carregar esta tela</h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            O frontend encontrou um erro inesperado. Recarregue a aplicação. Se continuar acontecendo,
            abra o Console do navegador e envie o erro exibido para análise.
          </p>
          <button
            className="mt-6 h-11 rounded-lg bg-primary px-5 text-sm font-semibold text-white hover:opacity-90"
            onClick={() => window.location.reload()}
          >
            Recarregar aplicação
          </button>
        </section>
      </main>
    )
  }
}
