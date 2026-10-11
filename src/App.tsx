import { ContactBand } from './components/ContactBand';
import { Differentials } from './components/Differentials';
import { Hero } from './components/Hero';
import { LiveChannels } from './components/LiveChannels';
import { PlansSection } from './components/PlansSection';
import { RegionSelect } from './components/RegionSelect';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import { useRegiao } from './hooks/useRegiao';

export default function App() {
  const { regiao, selecionar, trocar } = useRegiao();

  if (!regiao) {
    return <RegionSelect onSelecionar={selecionar} />;
  }

  return (
    <div className="min-h-screen overflow-x-hidden">
      <SiteHeader regiao={regiao} onTrocarRegiao={trocar} />
      <main>
        <Hero regiao={regiao} />
        <PlansSection regiao={regiao} />
        <Differentials />
        <LiveChannels />
        <ContactBand regiao={regiao} />
      </main>
      <SiteFooter regiao={regiao} onTrocarRegiao={trocar} />
    </div>
  );
}
