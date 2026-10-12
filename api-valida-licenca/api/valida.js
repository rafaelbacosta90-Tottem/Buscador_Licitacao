// api/valida.js
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
);

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ status: 'error', message: 'Método não permitido' });
  }

  const { chave, hwid } = req.body;

  if (!chave || !hwid) {
    return res.status(400).json({ status: 'error', message: 'Chave e HWID são obrigatórios' });
  }

  // 1. Busca a chave no banco
  const { data: licenca, error } = await supabase
    .from('licencas')
    .select('*')
    .eq('chave', chave)
    .single();

  if (error || !licenca) {
    return res.status(404).json({ status: 'invalid', message: 'Chave não encontrada' });
  }

  // 2. Verifica se está ativa
  if (!licenca.ativa) {
    return res.status(403).json({ status: 'invalid', message: 'Licença desativada' });
  }

  // 3. Verifica expiração
  const hoje = new Date();
  const expiracao = new Date(licenca.data_expiracao);
  if (hoje > expiracao) {
    return res.status(403).json({ status: 'expired', message: 'Licença expirada' });
  }

  // 4. Bloqueia múltiplos PCs (Vincula a chave ao HWID do primeiro PC que usou)
  if (!licenca.hwid) {
    // Registra o HWID no primeiro uso
    await supabase.from('licencas').update({ hwid: hwid }).eq('id', licenca.id);
  } else if (licenca.hwid !== hwid) {
    return res.status(403).json({ status: 'unauthorized', message: 'Chave em uso em outra máquina' });
  }

  return res.status(200).json({ status: 'success', message: 'Licença válida!' });
}