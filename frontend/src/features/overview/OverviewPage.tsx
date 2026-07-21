import { Row, Col } from 'antd';
import SectionHeader from '../../components/SectionHeader';
import HealthCard from './HealthCard';
import SnapshotCard from './SnapshotCard';
import AllocationPreview from './AllocationPreview';

export default function OverviewPage() {
  return (
    <div>
      <SectionHeader title="总览" subtitle="系统健康、市场快照与配置概览" />
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={12}>
          <HealthCard />
        </Col>
        <Col xs={24} lg={12}>
          <AllocationPreview />
        </Col>
        <Col span={24}>
          <SnapshotCard />
        </Col>
      </Row>
    </div>
  );
}